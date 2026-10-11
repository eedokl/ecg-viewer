"""Parse Apple Health ECG CSV files (supports English + German exports)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import numpy as np

DEFAULT_SAMPLE_RATE = 512
MIN_PEAKS_FOR_BPM = 2
MIN_BPM = 30
MAX_BPM = 220

if TYPE_CHECKING:
    from pathlib import Path

HEADER_ALIASES = {
    "name": "name",
    "date of birth": "dob",
    "geburtstag": "dob",
    "geburtsdatum": "dob",
    "recorded date": "recorded_at",
    "aufzeichnungsdatum": "recorded_at",
    "classification": "classification",
    "klassifizierung": "classification",
    "symptoms": "symptoms",
    "symptome": "symptoms",
    "software version": "software_version",
    "softwareversion": "software_version",
    "device": "device",
    "gerät": "device",
    "gerã¤t": "device",
    "sample rate": "sample_rate",
    "messrate": "sample_rate",
    "abtastrate": "sample_rate",
    "lead": "lead",
    "ableitung": "lead",
    "unit": "unit",
    "einheit": "unit",
    "average heart rate": "avg_hr",
    "durchschnittliche herzfrequenz": "avg_hr",
}


@dataclass
class ECGRecord:
    """Parsed Apple Health ECG record with metadata and µV samples."""

    path: Path
    name: str | None
    dob: str | None
    recorded_at: datetime | None
    classification: str | None
    symptoms: str | None
    device: str | None
    software_version: str | None
    sample_rate: int
    lead: str | None
    unit: str | None
    samples: np.ndarray  # microvolts
    avg_hr: int | None

    @property
    def duration_s(self) -> float:
        """Return the recording duration in seconds."""
        return len(self.samples) / self.sample_rate if self.sample_rate else 0.0


def _parse_sample_rate(raw: str | None) -> int:
    if not raw:
        return DEFAULT_SAMPLE_RATE
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits) if digits else DEFAULT_SAMPLE_RATE


def _parse_recorded_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _estimate_bpm(samples: np.ndarray, fs: int) -> int | None:
    if len(samples) < fs * 2:
        return None
    window = max(1, fs // 2)
    kernel = np.ones(window) / window
    baseline = np.convolve(samples, kernel, mode="same")
    sig = samples - baseline
    thresh = sig.mean() + 0.6 * sig.std()
    min_dist = int(fs * 0.33)
    peaks: list[int] = []
    last = -min_dist
    for i in range(1, len(sig) - 1):
        is_peak = sig[i] > thresh and sig[i] >= sig[i - 1] and sig[i] >= sig[i + 1]
        if is_peak and i - last >= min_dist:
            peaks.append(i)
            last = i
    if len(peaks) < MIN_PEAKS_FOR_BPM:
        return None
    intervals = np.diff(peaks) / fs
    bpm = 60.0 / intervals.mean()
    if MIN_BPM <= bpm <= MAX_BPM:
        return round(bpm)
    return None


def _decode_csv(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_meta_and_samples(text: str) -> tuple[dict[str, str], list[str]]:
    meta: dict[str, str] = {}
    samples_raw: list[str] = []
    in_samples = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue
        # A samples section begins after the "Name,µV" or "Lead I" marker line —
        # easier heuristic: a line is a sample if it parses as a float
        # (after comma→dot conversion) and has no alpha chars besides e/E/-.
        stripped = line.strip().lstrip("-")
        if stripped and all(ch.isdigit() or ch in ",.eE-+" for ch in stripped):
            try:
                float(line.strip().replace(",", "."))
            except ValueError:
                pass
            else:
                in_samples = True
                samples_raw.append(line.strip())
                continue
        if in_samples:
            break
        if "," in line:
            key, _, value = line.partition(",")
            key_norm = key.strip().lower().strip('"')
            value = value.strip().strip('"')
            if key_norm in HEADER_ALIASES:
                meta[HEADER_ALIASES[key_norm]] = value
    return meta, samples_raw


def parse_ecg(path: Path) -> ECGRecord:
    """Parse a single Apple Health ECG CSV.

    Args:
        path: Path to the Apple Health ECG CSV export file.

    Returns:
        Parsed :class:`ECGRecord` with metadata and µV samples.
    """
    # Apple Health exports are usually UTF-8, but some locales write cp1252.
    # Read bytes once and decode with a fallback so keys like "Gerät" are preserved.
    text = _decode_csv(path.read_bytes())
    meta, samples_raw = _extract_meta_and_samples(text)

    samples = np.array(
        [float(s.replace(",", ".")) for s in samples_raw], dtype=np.float32,
    )

    sample_rate = _parse_sample_rate(meta.get("sample_rate"))
    recorded_at = _parse_recorded_at(meta.get("recorded_at"))

    avg_hr_raw = meta.get("avg_hr")
    avg_hr: int | None = None
    if avg_hr_raw:
        digits = "".join(ch for ch in avg_hr_raw if ch.isdigit())
        if digits:
            avg_hr = int(digits)
    if avg_hr is None:
        avg_hr = _estimate_bpm(samples, sample_rate)

    return ECGRecord(
        path=path,
        name=meta.get("name"),
        dob=meta.get("dob"),
        recorded_at=recorded_at,
        classification=meta.get("classification"),
        symptoms=meta.get("symptoms") or None,
        device=meta.get("device"),
        software_version=meta.get("software_version"),
        sample_rate=sample_rate,
        lead=meta.get("lead"),
        unit=meta.get("unit") or "µV",
        samples=samples,
        avg_hr=avg_hr,
    )
