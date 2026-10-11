"""Scan the ECG folder and refresh the SQLite index incrementally."""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import db, samples
from .config import DATA_DIR
from .parser import parse_ecg

if TYPE_CHECKING:
    from pathlib import Path


def _record_meta(path: Path) -> dict:
    rec = parse_ecg(path)
    samples.write_cache(path, rec.samples, rec.sample_rate)
    recorded_at_iso = rec.recorded_at.isoformat() if rec.recorded_at else None
    recorded_date = rec.recorded_at.date().isoformat() if rec.recorded_at else None
    return {
        "recorded_at": recorded_at_iso,
        "recorded_date": recorded_date,
        "classification": rec.classification,
        "symptoms": rec.symptoms,
        "avg_hr": rec.avg_hr,
        "duration_s": rec.duration_s,
        "sample_rate": rec.sample_rate,
        "lead": rec.lead,
        "name": rec.name,
        "dob": rec.dob,
        "device": rec.device,
    }


def refresh(data_dir: Path | None = None) -> dict[str, int]:
    """Scan ``data_dir`` and update the SQLite index to match disk state.

    Args:
        data_dir: Folder containing the ECG CSV files; defaults to ``DATA_DIR``.

    Returns:
        Counts for ``added``, ``updated``, ``unchanged``, ``removed`` and ``total``.
    """
    data_dir = data_dir or DATA_DIR
    added = updated = unchanged = 0
    valid_paths: set[str] = set()
    if not data_dir.exists():
        return {"added": 0, "updated": 0, "unchanged": 0, "removed": 0, "total": 0}

    with db.connect() as conn:
        for path in sorted(data_dir.glob("*.csv")):
            valid_paths.add(str(path))
            mtime = path.stat().st_mtime
            existing = db.get_mtime(conn, path)
            if existing is None:
                db.upsert_record(conn, path=path, mtime=mtime, meta=_record_meta(path))
                added += 1
            elif existing != mtime:
                db.upsert_record(conn, path=path, mtime=mtime, meta=_record_meta(path))
                updated += 1
            else:
                unchanged += 1
        removed = db.prune_missing(conn, valid_paths)

    return {
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "removed": removed,
        "total": added + updated + unchanged,
    }
