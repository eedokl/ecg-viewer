"""SQLite index of ECG metadata. Samples stay on disk; only metadata is cached."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import TYPE_CHECKING

from .config import DB_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS ecg (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    recorded_at TEXT,
    recorded_date TEXT,
    classification TEXT,
    symptoms TEXT,
    avg_hr INTEGER,
    duration_s REAL,
    sample_rate INTEGER,
    lead TEXT,
    name TEXT,
    dob TEXT,
    device TEXT,
    mtime REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ecg_recorded_date ON ecg(recorded_date);
CREATE INDEX IF NOT EXISTS idx_ecg_recorded_at ON ecg(recorded_at);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with schema applied and auto-commit on exit."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_record(conn: sqlite3.Connection, *, path: Path, mtime: float, meta: dict) -> None:
    """Insert or update an ECG metadata row keyed by file path.

    Args:
        conn: Open SQLite connection.
        path: Source CSV path (used as unique key).
        mtime: File modification time, used to detect stale rows.
        meta: Parsed metadata fields matching the ``ecg`` table columns.
    """
    conn.execute(
        """
        INSERT INTO ecg (path, recorded_at, recorded_date, classification, symptoms,
                         avg_hr, duration_s, sample_rate, lead, name, dob, device, mtime)
        VALUES (:path, :recorded_at, :recorded_date, :classification, :symptoms,
                :avg_hr, :duration_s, :sample_rate, :lead, :name, :dob, :device, :mtime)
        ON CONFLICT(path) DO UPDATE SET
            recorded_at=excluded.recorded_at,
            recorded_date=excluded.recorded_date,
            classification=excluded.classification,
            symptoms=excluded.symptoms,
            avg_hr=excluded.avg_hr,
            duration_s=excluded.duration_s,
            sample_rate=excluded.sample_rate,
            lead=excluded.lead,
            name=excluded.name,
            dob=excluded.dob,
            device=excluded.device,
            mtime=excluded.mtime
        """,
        {"path": str(path), "mtime": mtime, **meta},
    )


def get_mtime(conn: sqlite3.Connection, path: Path) -> float | None:
    """Return the stored mtime for ``path`` or ``None`` if unknown.

    Args:
        conn: Open SQLite connection.
        path: Source CSV path.

    Returns:
        The mtime previously stored for ``path``, or ``None`` if the row is absent.
    """
    row = conn.execute("SELECT mtime FROM ecg WHERE path = ?", (str(path),)).fetchone()
    return row["mtime"] if row else None


def list_records(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[sqlite3.Row]:
    """Return ECG rows filtered by an optional recorded-date range.

    Args:
        conn: Open SQLite connection.
        date_from: Inclusive lower bound as ``YYYY-MM-DD``, or ``None``.
        date_to: Inclusive upper bound as ``YYYY-MM-DD``, or ``None``.

    Returns:
        Matching rows, newest first by ``recorded_at``.
    """
    sql = "SELECT * FROM ecg WHERE 1=1"
    params: list = []
    if date_from:
        sql += " AND recorded_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND recorded_date <= ?"
        params.append(date_to)
    sql += " ORDER BY recorded_at DESC"
    return conn.execute(sql, params).fetchall()


def get_record(conn: sqlite3.Connection, ecg_id: int) -> sqlite3.Row | None:
    """Return the row for a single ECG id, or ``None`` if not found.

    Args:
        conn: Open SQLite connection.
        ecg_id: Primary key of the ECG row.

    Returns:
        The row with matching id, or ``None`` if absent.
    """
    return conn.execute("SELECT * FROM ecg WHERE id = ?", (ecg_id,)).fetchone()


def prune_missing(conn: sqlite3.Connection, valid_paths: set[str]) -> int:
    """Delete rows whose ``path`` is not in ``valid_paths``.

    Args:
        conn: Open SQLite connection.
        valid_paths: Paths (as strings) that currently exist on disk.

    Returns:
        Number of rows removed.
    """
    rows = conn.execute("SELECT id, path FROM ecg").fetchall()
    stale = [r["id"] for r in rows if r["path"] not in valid_paths]
    if stale:
        conn.executemany("DELETE FROM ecg WHERE id = ?", [(sid,) for sid in stale])
    return len(stale)
