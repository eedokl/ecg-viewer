"""FastAPI application."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import db, ingest, samples
from .pdf import PDFOptions, export_pdf

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

STATIC_DIR = Path(__file__).resolve().parent / "static"

HTTP_NOT_FOUND = 404


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Refresh the metadata index once at startup."""
    ingest.refresh()
    yield


app = FastAPI(title="ECG Viewer", lifespan=lifespan)


@app.get("/api/ecgs")
def list_ecgs(
    date_from: Annotated[str | None, Query(description="YYYY-MM-DD inclusive")] = None,
    date_to: Annotated[str | None, Query(description="YYYY-MM-DD inclusive")] = None,
) -> list[dict[str, Any]]:
    """Return ECG metadata filtered by optional recorded-date range.

    Args:
        date_from: Inclusive lower bound as ``YYYY-MM-DD``.
        date_to: Inclusive upper bound as ``YYYY-MM-DD``.

    Returns:
        List of ECG metadata dicts (newest first).
    """
    with db.connect() as conn:
        rows = db.list_records(conn, date_from=date_from, date_to=date_to)
    return [
        {
            "id": r["id"],
            "recorded_at": r["recorded_at"],
            "recorded_date": r["recorded_date"],
            "classification": r["classification"],
            "symptoms": r["symptoms"],
            "avg_hr": r["avg_hr"],
            "duration_s": r["duration_s"],
            "sample_rate": r["sample_rate"],
            "lead": r["lead"],
            "name": r["name"],
            "dob": r["dob"],
            "device": r["device"],
        }
        for r in rows
    ]


@app.get("/api/ecgs/{ecg_id}")
def get_ecg(
    ecg_id: int,
    downsample: Annotated[int, Query(ge=1, le=16)] = 2,
) -> dict[str, Any]:
    """Return metadata and downsampled mV samples for a single ECG.

    Args:
        ecg_id: Primary key of the ECG row.
        downsample: Integer stride applied to the sample array.

    Returns:
        Metadata plus samples in mV with the effective sample rate.

    Raises:
        HTTPException: If the ECG id does not exist.
    """
    with db.connect() as conn:
        row = db.get_record(conn, ecg_id)
    if row is None:
        raise HTTPException(HTTP_NOT_FOUND, "ECG not found")
    uv, fs = samples.load_samples(Path(row["path"]))
    if downsample > 1:
        uv = uv[::downsample]
        effective_fs = fs / downsample
    else:
        effective_fs = fs
    # Convert to mV for display
    mv = (uv / 1000.0).astype(np.float32)
    return {
        "id": row["id"],
        "recorded_at": row["recorded_at"],
        "classification": row["classification"],
        "symptoms": row["symptoms"],
        "avg_hr": row["avg_hr"],
        "duration_s": row["duration_s"],
        "sample_rate": float(effective_fs),
        "original_sample_rate": fs,
        "lead": row["lead"],
        "name": row["name"],
        "dob": row["dob"],
        "samples_mv": mv.tolist(),
    }


@app.post("/api/refresh")
def refresh() -> dict[str, int]:
    """Rebuild the metadata index from disk and return refresh counters."""
    return ingest.refresh()


@app.get("/api/export.pdf")
def export(
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    ecg_id: Annotated[
        int | None,
        Query(description="Single ECG by id (overrides date range)"),
    ] = None,
) -> Response:
    """Render one or many ECGs to a printable PDF.

    Args:
        date_from: Inclusive lower bound as ``YYYY-MM-DD`` (ignored if ``ecg_id`` is set).
        date_to: Inclusive upper bound as ``YYYY-MM-DD`` (ignored if ``ecg_id`` is set).
        ecg_id: If provided, export just this ECG.

    Returns:
        A PDF response with a content-disposition attachment header.

    Raises:
        HTTPException: If ``ecg_id`` is provided but not found.
    """
    with db.connect() as conn:
        if ecg_id is not None:
            row = db.get_record(conn, ecg_id)
            if row is None:
                raise HTTPException(HTTP_NOT_FOUND, "ECG not found")
            rows = [row]
        else:
            rows = db.list_records(conn, date_from=date_from, date_to=date_to)

    paths = [Path(r["path"]) for r in rows]
    title = "EKG Export"
    if ecg_id is not None and rows:
        title = f"EKG {rows[0]['recorded_date']}"
    elif date_from or date_to:
        title = f"EKG {date_from or '…'} – {date_to or '…'}"
    pdf_bytes = export_pdf(paths, PDFOptions(title=title))
    filename = title.replace(" ", "_").replace("/", "-") + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class NoCacheStatic(StaticFiles):
    """Static files handler that disables client-side caching.

    Users were hitting stale JS during iteration — ``Cache-Control: no-store``
    guarantees the browser re-fetches on every request.
    """

    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        """Return the static response with ``Cache-Control: no-store`` applied.

        Args:
            path: Requested static path (relative to the mount directory).
            scope: ASGI scope dict.

        Returns:
            The upstream response with caching disabled.
        """
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-store"
        return resp


app.mount("/", NoCacheStatic(directory=STATIC_DIR, html=True), name="static")
