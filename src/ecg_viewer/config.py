"""Runtime configuration resolved from environment variables with local defaults."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATA_DIR = Path(
    r"C:\Users\Oliver-2018\Desktop\Claude\apple_health_export\electrocardiograms",
)

DATA_DIR = Path(os.environ.get("ECG_DATA_DIR", DEFAULT_DATA_DIR))
_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = Path(os.environ.get("ECG_DB_PATH", _ROOT / ".ecg_viewer.db"))
PARQUET_CACHE_DIR = Path(os.environ.get("ECG_PARQUET_CACHE", _ROOT / ".ecg_cache"))
