# SmartSlot

A college timetable scheduler. A coordinator imports the semester's data from CSV files, generates a timetable that has
**no teacher, room or batch clashes**, understands anything that could not be placed, edits the result safely, and
publishes / exports a verified version (CSV and PDF).

## What is real and what is sample

| Real, implemented and tested | Sample / not included |
|------------------------------|-----------------------|
| CSV import with row-level validation (file, row, field, value, how to fix) | The data in `sample_data/` is **fictional demo data** (6 teachers, 5 subjects, 3 batches, 4 rooms) |
| Constraint-based scheduler + an independent validator (teacher / room / batch overlap, availability, capacity, room type, breaks, durations) | **No live ERP connection.** SmartSlot reads CSV files that you export from an ERP or spreadsheet using the documented template |
| Draft / published / archived versions, restore, compare, publish gates | No login or roles (single coordinator view) |
| Safe manual edits with explanations and suggested alternatives | No notifications, no multi-campus support |
| CSV and PDF export, analytics | |

CSV format and error explanations: [`sample_data/README.md`](sample_data/README.md).

## Requirements

* Windows PowerShell (the scripts below), Python 3.11+ (developed on 3.13)
* Node.js 18+ only for the web UI (`frontend/`, when present)

## Setup (once)

```powershell
cd "path\to\ai timetable"
python -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt
```

## Run

```powershell
.\start.ps1                      # API on :8000 and, if frontend\package.json exists, the web UI on :5173
.\start.ps1 -Backend             # API only
.\start.ps1 -Frontend            # web UI only
.\start.ps1 -Backend -LoadSample # also wipe the database and load the feasible demo dataset
.\start.ps1 -Reload              # restart the API when backend code changes (development)
```

Each server opens in its own window; close the window to stop it. The script creates the Python environment on first
run if it is missing and runs `npm install` for the UI when `node_modules` is absent.

Without the script:

```powershell
cd backend
$env:SMARTSLOT_DEV = "1"         # enables POST /api/dev/reset (demo / tests only)
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

| URL | What |
|-----|------|
| http://localhost:8000/docs | Interactive API documentation (Swagger UI) |
| http://localhost:8000/api/health | Health check |
| http://localhost:5173 | Web UI (Vite dev server; its `/api` proxy must target `http://127.0.0.1:8000`) |

The SQLite database is created automatically at `backend/data/smartslot.db` (git-ignored). To start over, call
`POST /api/dev/reset` (dev mode only; add `?sample=feasible` to reload the demo) or delete the file while the server is stopped.
Set `SMARTSLOT_DB` to use another file.

### Try it without the UI

```powershell
curl.exe -X POST "http://localhost:8000/api/datasets/load-sample?kind=feasible"
curl.exe -X POST "http://localhost:8000/api/datasets/1/generate"
curl.exe -o timetable.pdf "http://localhost:8000/api/versions/1/export.pdf?view=batch"
```

## Test

```powershell
cd backend
.venv\Scripts\python -m pytest          # engine + importer + API (about 200 tests, ~10 s)
```

The API tests use a temporary database, so they never touch `backend/data/`.

## Project layout

```
backend/app/engine/      pure scheduling engine: generate, validate, suggest, analytics (no web / DB code)
backend/app/importer/    CSV parsing and row-level validation -> ImportReport
backend/app/repo/        SQLite storage (datasets, versions)      backend/app/db.py  schema + transactions
backend/app/services/    import, versions, editing, compare, enrichment (names/times for the UI)
backend/app/api/         FastAPI routes under /api                backend/app/export/  CSV + PDF (ReportLab)
backend/tests/           pytest suites
sample_data/             feasible/ infeasible/ invalid/ datasets and blank templates/
docs/                    PRD.md, ARCHITECTURE.md, API.md (endpoint reference)
```

## Documentation

* [`docs/PRD.md`](docs/PRD.md) - product requirements
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) - design decisions, engine API
* [`docs/API.md`](docs/API.md) - every endpoint with request / response JSON and TypeScript-style shapes

## Known limitations

* Fixed weekly timetable (no per-week exceptions); one dataset = one semester.
* Teacher is fixed per requirement by the CSV; a coordinator can reassign it in an edit, and the validator checks the result.
* The scheduler is a bounded search: on large or very tight data it reports "no complete solution found within the search
  limit" and returns the best partial timetable rather than claiming impossibility.
* PDF text uses a system Unicode font when found (Segoe UI / Arial / DejaVu), otherwise Helvetica (Latin text only).
