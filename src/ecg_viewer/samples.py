"""Parquet cache for ECG sample arrays. One file per CSV."""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import PARQUET_CACHE_DIR

if TYPE_CHECKING:
    from pathlib import Path


def _cache_path(source_csv: Path) -> Path:
    # Use a hash of the absolute path so the cache layout stays flat and stable.
    h = hashlib.sha1(str(source_csv.resolve()).encode("utf-8")).hexdigest()[:16]
    return PARQUET_CACHE_DIR / f"{source_csv.stem}-{h}.parquet"


def write_cache(source_csv: Path, samples_uv: np.ndarray, sample_rate: int) -> Path:
    PARQUET_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(source_csv)
    table = pa.table({"uv": pa.array(samples_uv, type=pa.float32())})
    meta = {b"sample_rate": str(int(sample_rate)).encode("utf-8")}
    table = table.replace_schema_metadata(meta)
    pq.write_table(table, path, compression="zstd")
    return path


def read_cache(source_csv: Path) -> tuple[np.ndarray, int] | None:
    path = _cache_path(source_csv)
    if not path.exists():
        return None
    table = pq.read_table(path)
    uv = table.column("uv").to_numpy(zero_copy_only=False).astype(np.float32, copy=False)
    meta = table.schema.metadata or {}
    sample_rate = int(meta.get(b"sample_rate", b"512"))
    return uv, sample_rate


def load_samples(source_csv: Path) -> tuple[np.ndarray, int]:
    """Return (samples_uv, sample_rate). Uses parquet cache if present, else parses CSV."""
    cached = read_cache(source_csv)
    if cached is not None:
        return cached
    from .parser import parse_ecg  # avoid import cycle
    rec = parse_ecg(source_csv)
    write_cache(source_csv, rec.samples, rec.sample_rate)
    return rec.samples, rec.sample_rate


def invalidate(source_csv: Path) -> None:
    path = _cache_path(source_csv)
    if path.exists():
        path.unlink()
