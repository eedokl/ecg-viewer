# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Use `uv` (never `pip`). All commands run from the repo root on Windows bash/PowerShell.

```bash
uv sync                                 # install deps (incl. dev)
uv run ecg-viewer                       # start FastAPI on http://127.0.0.1:8000
uv run ecg-viewer --reload              # dev mode with auto-reload
uv run ecg-viewer --refresh-only        # rebuild SQLite index + Parquet cache, then exit
uv run ecg-viewer --data-dir <path>     # override ECG source folder for this run
uv build                                # produce wheel + sdist in dist/ (hatchling)
```

There are no tests yet. For a one-off smoke check, invoke modules directly with the venv python, e.g.
`./.venv/Scripts/python -c "from ecg_viewer import ingest; print(ingest.refresh())"`.

## Architecture

The app reads Apple Health ECG CSV exports and serves two views: an iPhone-style single-ECG viewer and a stacked **Vergleich** page. A printable PDF export is the third deliverable.

**Data flow.** On server startup (`lifespan` in `main.py`) `ingest.refresh()` walks `DATA_DIR`, parses every `*.csv` via `parser.parse_ecg`, and writes two caches:

- **SQLite** (`.ecg_viewer.db`) — metadata only (date, classification, symptoms, estimated BPM, device, sample rate, lead). Rebuilt incrementally by mtime; stale rows pruned.
- **Parquet** (`.ecg_cache/{stem}-{sha1}.parquet`, zstd) — the raw µV sample array with `sample_rate` in schema metadata. Read by `samples.load_samples()` which falls back to re-parsing the CSV on miss.

The frontend never touches CSVs; it hits `/api/ecgs` (list) and `/api/ecgs/{id}?downsample=N` (samples in mV). Downsampling is server-side, and `effective_fs = fs / downsample` is returned so the client can draw correctly.

**Parser quirks (`parser.py`).** Apple Health exports are German-locale on this machine — keys are `Aufzeichnungsdatum`, `Klassifizierung`, `Messrate`, `Gerät`, `Ableitung`, and samples use **comma as decimal separator**. `HEADER_ALIASES` normalizes German + English + the common `GerÃ¤t` mojibake to canonical keys. The file is decoded through a utf-8 → cp1252 → latin-1 chain so mixed-encoding files round-trip cleanly. The samples section is detected by a "first numeric line" heuristic, not by a fixed header count — don't hardcode the header size. BPM is estimated from R-peak detection in `_estimate_bpm` when the CSV doesn't carry an Apple-provided heart rate (which is the common case for this export).

**PDF (`pdf.py`).** Printable (white bg, pink grid) — explicitly **not** the dark UI style. Paper conventions are hard-coded: 25 mm/s, 10 mm/mV, 5 s strips, ReportLab A4, with strips flowing onto additional pages when needed. One ECG per page; multi-record exports call `render_record` + `showPage` per record.

**Frontend (`src/ecg_viewer/static/`).** Vanilla JS, no build step, served via a `NoCacheStatic` subclass that sets `Cache-Control: no-store` — needed because users were hitting stale cached JS during iteration. Script tags also carry `?v=N` cache-busters — bump the version when you change the JS. Two pages:

- `index.html` + `app.js` — single-ECG viewer. Canvas paints a 6-row ECG strip split at 5 s each, matching the PDF layout, with drawing wrapped in `requestAnimationFrame` and a `selectSeq` counter guarding against out-of-order fetches on rapid clicks.
- `compare.html` + `compare.js` — stacked per-ECG rows, each a 280px meta block + a fixed-width (220 px/s) canvas inside a horizontally-scrollable container. `.ecg-row { flex-shrink: 0 }` + `grid-template-columns: 280px minmax(0, 1fr)` are load-bearing: without them, adding rows compressed the canvases and killed the horizontal scrollbar.

**Config (`config.py`).** `DATA_DIR`, `DB_PATH`, and `PARQUET_CACHE_DIR` are resolved from env vars (`ECG_DATA_DIR`, `ECG_DB_PATH`, `ECG_PARQUET_CACHE`) with hard-coded defaults pointing into `C:\Users\Oliver-2018\Desktop\Claude\apple_health_export\electrocardiograms`. This default is intentionally absolute — treat it as local-dev-only.

## Conventions

- The backend speaks German to the user (labels, PDF headers). Keep new UI copy German unless asked otherwise.
- `samples_uv` (float32 µV) is the canonical internal unit; conversion to mV happens at the edge (API response and PDF renderer). Don't pre-convert during ingest — the Parquet cache must stay in µV.
- When schema changes in `db.py` require a reindex, delete `.ecg_viewer.db` and `.ecg_cache/` and re-run `--refresh-only`; there's no migration framework.
