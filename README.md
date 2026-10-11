# ECG Viewer

Apple Health ECG viewer with an iPhone-style display and printable PDF export for sharing with a doctor.

- **Backend:** FastAPI + pandas + pyarrow + SQLite
- **Frontend:** Vanilla HTML/JS (Canvas)
- **PDF:** reportlab, white background, 25 mm/s · 10 mm/mV grid

## Setup

```powershell
cd ecg-viewer
uv sync
.venv\scripts\activate
```

## Run

```powershell
uv run ecg-viewer
# → http://127.0.0.1:8000
```

Options:
```powershell
uv run ecg-viewer --host 0.0.0.0 --port 8080 --reload
uv run ecg-viewer --refresh-only           # rebuild index & Parquet cache
uv run ecg-viewer --data-dir electrocardiograms
```

## Data

By default the app reads from:
```
$HOME\Desktop\Claude\apple_health_export\electrocardiograms
```

Override with `ECG_DATA_DIR` (env var) or `--data-dir`.

On startup the app:
1. Scans all `*.csv` in the data dir.
2. Writes metadata (date, classification, BPM, symptoms, …) into `.ecg_viewer.db` (SQLite).
3. Caches each recording's samples as Parquet (`.ecg_cache/`) for fast reads.

The cache refreshes incrementally — files whose mtime hasn't changed are skipped.

## Features

- Sidebar list of all ECG recordings with date-range filter.
- Single-recording viewer styled like the iPhone Health app (dark UI, red trace).
- Heart rate estimation (if not present in the CSV).
- PDF export — **current recording**, **date range**, or **all** — printable white background.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/ecgs?date_from=&date_to=` | List recordings |
| GET | `/api/ecgs/{id}?downsample=2` | Samples + metadata |
| POST | `/api/refresh` | Re-scan data dir |
| GET | `/api/export.pdf?ecg_id=` | PDF of one recording |
| GET | `/api/export.pdf?date_from=&date_to=` | PDF range / all |
