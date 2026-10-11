"""CLI entrypoint: ``ecg-viewer`` or ``python -m ecg_viewer``."""

from __future__ import annotations

import argparse
import os
import sys

import uvicorn

from . import ingest


def main(argv: list[str] | None = None) -> int:
    """Parse CLI flags and either refresh the cache or start the web server.

    Args:
        argv: Optional command-line arguments (defaults to :data:`sys.argv`).

    Returns:
        Process exit code. ``0`` on success.
    """
    parser = argparse.ArgumentParser(prog="ecg-viewer", description="Apple Health ECG viewer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev)")
    parser.add_argument("--data-dir", help="Override ECG_DATA_DIR for this run")
    parser.add_argument(
        "--refresh-only",
        action="store_true",
        help="Rebuild the SQLite index and Parquet cache, then exit.",
    )
    args = parser.parse_args(argv)

    if args.data_dir:
        os.environ["ECG_DATA_DIR"] = args.data_dir

    if args.refresh_only:
        stats = ingest.refresh()
        print(f"refreshed: {stats}")
        return 0

    uvicorn.run(
        "ecg_viewer.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
