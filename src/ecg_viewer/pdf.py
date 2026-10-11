"""Apple-Health-style ECG PDF — printable (white background, red grid)."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas

from .parser import ECGRecord, parse_ecg

if TYPE_CHECKING:
    from pathlib import Path

# ECG paper convention
MM_PER_S = 25.0
MM_PER_MV = 10.0
STRIP_SECONDS = 5.0
ROW_HEIGHT_MM = 24.0  # ±1.2 mV visual range
ROW_GAP_MM = 4.0

PAGE_W, PAGE_H = A4
MARGIN = 12 * mm

GRID_MINOR = (1.0, 0.82, 0.82)  # light pink
GRID_MAJOR = (0.90, 0.55, 0.55)  # darker pink
TRACE_COLOR = (0.10, 0.10, 0.10)
HEADER_COLOR = (0.20, 0.20, 0.20)


@dataclass
class PDFOptions:
    title: str = "ECG Export"


def _draw_grid(c: pdf_canvas.Canvas, x: float, y: float, w_mm: float, h_mm: float) -> None:
    """Draw 1mm minor + 5mm major grid inside a box anchored at (x,y) bottom-left (mm units)."""
    x0, y0 = x * mm, y * mm
    # minor
    c.setStrokeColorRGB(*GRID_MINOR)
    c.setLineWidth(0.2)
    for i in range(int(w_mm) + 1):
        c.line(x0 + i * mm, y0, x0 + i * mm, y0 + h_mm * mm)
    for j in range(int(h_mm) + 1):
        c.line(x0, y0 + j * mm, x0 + w_mm * mm, y0 + j * mm)
    # major (every 5mm)
    c.setStrokeColorRGB(*GRID_MAJOR)
    c.setLineWidth(0.5)
    for i in range(0, int(w_mm) + 1, 5):
        c.line(x0 + i * mm, y0, x0 + i * mm, y0 + h_mm * mm)
    for j in range(0, int(h_mm) + 1, 5):
        c.line(x0, y0 + j * mm, x0 + w_mm * mm, y0 + j * mm)
    # outer border
    c.setStrokeColorRGB(*GRID_MAJOR)
    c.setLineWidth(0.8)
    c.rect(x0, y0, w_mm * mm, h_mm * mm, stroke=1, fill=0)


def _draw_strip(
    c: pdf_canvas.Canvas,
    samples_mv: np.ndarray,
    fs: int,
    x_mm: float,
    y_mm: float,
    seconds: float = STRIP_SECONDS,
) -> None:
    w_mm = seconds * MM_PER_S
    h_mm = ROW_HEIGHT_MM
    _draw_grid(c, x_mm, y_mm, w_mm, h_mm)

    n = min(len(samples_mv), int(seconds * fs))
    if n < 2:
        return
    xs = np.linspace(0, w_mm, n) + x_mm
    mid = y_mm + h_mm / 2.0
    # Clip mV to ±(h_mm/2)/MM_PER_MV
    max_mv = (h_mm / 2.0) / MM_PER_MV
    ys = np.clip(samples_mv[:n], -max_mv, max_mv) * MM_PER_MV + mid

    c.setStrokeColorRGB(*TRACE_COLOR)
    c.setLineWidth(0.7)
    p = c.beginPath()
    p.moveTo(xs[0] * mm, ys[0] * mm)
    for xi, yi in zip(xs[1:], ys[1:], strict=False):
        p.lineTo(xi * mm, yi * mm)
    c.drawPath(p, stroke=1, fill=0)


def _draw_header(c: pdf_canvas.Canvas, rec: ECGRecord) -> float:
    """Draw the header block; returns the y (mm) of the bottom of the header."""
    top_mm = (PAGE_H - MARGIN) / mm
    left_mm = MARGIN / mm

    c.setFillColorRGB(*HEADER_COLOR)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left_mm * mm, (top_mm - 6) * mm, "Elektrokardiogramm (EKG)")

    recorded = rec.recorded_at.strftime("%d.%m.%Y  %H:%M") if rec.recorded_at else "—"
    classification = rec.classification or "—"
    c.setFont("Helvetica", 11)
    c.drawString(left_mm * mm, (top_mm - 12) * mm, f"{recorded}")
    c.drawString(left_mm * mm, (top_mm - 17) * mm, f"Klassifizierung: {classification}")

    hr = f"{rec.avg_hr} BPM" if rec.avg_hr else "—"
    symp = rec.symptoms or "Keine"
    name = rec.name or ""
    dob = rec.dob or ""
    c.drawRightString((PAGE_W - MARGIN), (top_mm - 6) * mm - 6, name)
    c.setFont("Helvetica", 9)
    c.drawRightString((PAGE_W - MARGIN), (top_mm - 12) * mm - 2, f"Geb.: {dob}")
    c.setFont("Helvetica", 11)
    c.drawString((left_mm + 70) * mm, (top_mm - 12) * mm, f"⌀ Herzfrequenz: {hr}")
    c.drawString((left_mm + 70) * mm, (top_mm - 17) * mm, f"Symptome: {symp}")

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(
        left_mm * mm,
        (top_mm - 22) * mm,
        f"{rec.lead or 'Lead I'} · {int(rec.sample_rate)} Hz · 25 mm/s · 10 mm/mV",
    )
    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.setLineWidth(0.4)
    c.line(MARGIN, (top_mm - 24) * mm, PAGE_W - MARGIN, (top_mm - 24) * mm)
    return top_mm - 28


def render_record(c: pdf_canvas.Canvas, rec: ECGRecord) -> None:
    """Render one ECG record onto the current page; may add additional pages."""
    # Convert µV → mV
    samples_mv = rec.samples.astype(np.float64) / 1000.0
    fs = rec.sample_rate

    header_bottom_mm = _draw_header(c, rec)
    left_mm = MARGIN / mm
    bottom_mm = MARGIN / mm

    total_seconds = len(samples_mv) / fs
    strips_needed = int(np.ceil(total_seconds / STRIP_SECONDS))

    available_h_mm = header_bottom_mm - bottom_mm
    rows_per_page = max(1, int(available_h_mm // (ROW_HEIGHT_MM + ROW_GAP_MM)))

    y_cursor_mm = header_bottom_mm - ROW_HEIGHT_MM
    rows_on_page = 0
    for strip_idx in range(strips_needed):
        start = int(strip_idx * STRIP_SECONDS * fs)
        end = int(start + STRIP_SECONDS * fs)
        seg = samples_mv[start:end]
        actual_seconds = len(seg) / fs
        _draw_strip(c, seg, fs, left_mm, y_cursor_mm, seconds=max(actual_seconds, 0.1))

        # label time
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.setFont("Helvetica", 7)
        c.drawString(left_mm * mm, (y_cursor_mm - 3) * mm, f"{strip_idx * STRIP_SECONDS:.0f}s")

        rows_on_page += 1
        y_cursor_mm -= ROW_HEIGHT_MM + ROW_GAP_MM
        if rows_on_page >= rows_per_page and strip_idx < strips_needed - 1:
            c.showPage()
            rows_on_page = 0
            y_cursor_mm = (PAGE_H - MARGIN) / mm - ROW_HEIGHT_MM


def export_pdf(records: list[Path], options: PDFOptions | None = None) -> bytes:
    options = options or PDFOptions()
    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(options.title)
    c.setAuthor("ECG Viewer")

    if not records:
        c.setFont("Helvetica", 14)
        c.drawString(MARGIN, PAGE_H - MARGIN - 20, "Keine EKG-Aufzeichnungen im gewählten Zeitraum.")
        c.showPage()
        c.save()
        return buf.getvalue()

    for _idx, path in enumerate(records):
        rec = parse_ecg(path)
        render_record(c, rec)
        c.showPage()
    c.save()
    return buf.getvalue()
