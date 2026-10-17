# SmartSlot — Architecture & Decisions

Authoritative design decisions for all builders. `docs/PRD.md` is the product spec; this file resolves ambiguity. If the two conflict, PRD wins on behaviour, this file wins on implementation choices.

## Stack
- **Backend**: Python 3.13, FastAPI, Pydantic v2, SQLite (stdlib `sqlite3` or SQLAlchemy — builder's choice, keep it simple), `reportlab` for PDF, `python-multipart` for uploads, `pytest` + FastAPI `TestClient`. Port **8000**. DB file at `backend/data/smartslot.db` (gitignored, auto-created, re-seedable).
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS. Port **5173**; Vite dev-server proxies `/api` → `http://127.0.0.1:8000` (**use 127.0.0.1, not `localhost`**: Node resolves `localhost` to `::1` first and uvicorn listens on the IPv4 loopback only). No auth. Polished, clean, light theme, college-admin feel; responsive for laptop and tablet (>= 768px).
- **Run scripts** at repo root: `start.ps1` (starts both servers) and `README.md` with exact commands.
- Everything runs offline from local sample data.

## Repo layout
```
docs/PRD.md  docs/ARCHITECTURE.md  docs/API.md (written by backend builder)
PROGRESS.md                      # orchestrator-maintained status
backend/app/engine/              # PURE python, no FastAPI/DB imports (DONE, phase 1):
                                 #   models, expand, candidates, analysis (static capacity), soft, scheduler (generate),
                                 #   explain, validator, suggest (suggest_slots/validate_move/validate_place),
                                 #   revalidation, analytics, loaders (simple CSV loader for tests/demo), labels, lookup
backend/app/importer/            # CSV parsing + row-level validation (phase 2, DONE): schema, reader, fields, entities,
                                 #   crossref, intake (uploads/zip safety), pipeline, templates, samples, report
backend/app/db.py, settings.py   # SQLite schema + transactions; limits/paths (DONE)
backend/app/repo/                # datasets.py, versions.py: SQL only, no business rules
backend/app/services/            # datasets, versions (generate/publish/restore), editing, compare, state, enrich
backend/app/api/                 # FastAPI routers mounted under /api: system, datasets, versions, editing, exports
backend/app/export/              # csv_export.py, pdf_export.py (ReportLab), fonts.py
backend/app/main.py, schemas.py, requests.py, errors.py, middleware.py
backend/tests/                   # engine (88) + importer + API tests (204 total)
backend/scripts/demo_generate.py # prints per-batch grids: python scripts/demo_generate.py [dir] [--view batch|teacher|room]
frontend/src/...
sample_data/feasible/*.csv       # demo dataset (completes, 60/60 sessions)
sample_data/infeasible/*.csv     # DS Lab 4x/week per batch -> partial 63/66 (see EXPECTED_RESULT.md)
sample_data/invalid/*.csv        # 35 deliberate row errors (see EXPECTED_ERRORS.md) to demo row-level validation
sample_data/templates/*.csv      # blank header-only templates
sample_data/README.md            # CSV template documentation (columns, rules, how to fix errors)
demo/                            # screenshots, scripts, final mp4
```

## Domain conventions
- **Days**: `Mon..Fri` default (configurable list, e.g. add `Sat`). **Periods**: 1-based integers. Config defines each period: `period, start, end, is_break`. A break period (e.g., lunch) can never hold a session and a multi-period session may NOT span across a break or a non-consecutive period.
- **Break numbering (decided in phase 1)**: a break is its own numbered period row. Demo day = periods `1 2 3`, lunch `4` (`is_break=1`), periods `5 6 7` (six teaching periods, seven grid rows). Messages say "Period 5" for the first class after lunch; the UI renders `is_break` rows as a shaded, non-bookable row. Teaching periods are exactly the non-break periods.
- **CSV file set (deviation from the original draft, which had `config.csv`)**: `teachers.csv, subjects.csv, batches.csv, rooms.csv, requirements.csv, days.csv (column: day), periods.csv (period,start,end,is_break)` are required; `availability.csv` is optional (default = everything available). Columns are documented in `sample_data/README.md`. `PUT /datasets/{id}/config` still edits days + periods.
- **Row numbers** in import errors are spreadsheet rows: header = row 1, first data row = row 2 (`sample_data/invalid/EXPECTED_ERRORS.md` lists 35 expected errors using this convention).
- **Session type**: subject `session_type` ∈ `lecture | practical`. **Room type** ∈ `classroom | lab`. Practical ⇒ lab only. Lecture ⇒ classroom only (labs are not used for lectures).
- **duration** = number of consecutive periods (lecture usually 1, practical usually 2).
- **Capacity rule**: `room.capacity >= batch.student_count`.
- **Availability**: rows `resource_id,day,period,available`. `resource_id` may be a teacher_id or room_id. **Default = available**; rows with `available=0/false/no` mark unavailability (rows with 1 are accepted and ignored). A session placed over any period where its teacher or room is unavailable is a hard violation.
- **Session expansion**: each requirement (`subject_id,batch_id,teacher_id,sessions_per_week,duration`) expands into `sessions_per_week` sessions with ids like `CS101-CE-A-1`. Teacher is fixed by the requirement (manual edit can change it, validated). The engine chooses day, start_period, room.
- **Identity**: all IDs are unique strings; duplicates are import errors.
- **Department/semester**: teachers/subjects carry `department_id`; batches carry `semester` (+ optional `department_id`). A dataset has `semester` and `name`. Resources (teachers, rooms) are checked globally across the dataset.
- **Soft scoring** (only tie-breakers, never override hard): spread a subject's sessions across different days, even per-day load per batch, avoid >3 consecutive periods for a teacher, minimize teacher gaps, avoid last period if alternatives exist.
- **Determinism**: same input ⇒ same output (fixed ordering, no unseeded randomness). Validator results sorted deterministically.

## Scheduler (engine)
Constraint-based backtracking: expand → compute candidate (day,start,room) per session → order most-constrained-first (fewest candidates, longest duration, busiest teacher) → forward-check → backtrack, bounded by `max_nodes` (default 200_000) and `time_limit_s` (default 10). Returns `{status, scheduled[], unscheduled[{session, reasons[]}], stats{nodes, elapsed_ms, hit_limit}, validation}`.
- `status`: `complete` (all sessions placed AND independent validator reports 0 hard conflicts) | `partial` (some unscheduled; placed ones valid) | `failed`.
- If limit hit without a full solution: return best partial found, message must say *"No complete solution found within the search limit"*, **never** claim infeasibility as proof. When a session provably has zero candidate slots (static analysis) say exactly why (teacher unavailable, no lab large enough, teacher overload, etc.).
- Unscheduled reasons are human-readable, e.g. `"Dr. Sharma (CS101) has only 4 free periods per week but 6 sessions are required"`.
- The independent validator (`validate(dataset, entries) -> ValidationReport`) shares NO placement logic with the solver; it recomputes everything from the entry list. It is used for final check after generation, on every edit, and before publish.

## Validator conflict types (stable string codes)
`TEACHER_OVERLAP, ROOM_OVERLAP, BATCH_OVERLAP, TEACHER_UNAVAILABLE, ROOM_UNAVAILABLE, ROOM_CAPACITY, ROOM_TYPE, INVALID_DURATION, OUTSIDE_WORKING_HOURS, BLOCKED_PERIOD, INVALID_REFERENCE, MISSING_SESSION`.
Each conflict: `{code, severity: "error"|"warning", message, day, period, entry_ids[], involved: {teacher_id?, room_id?, batch_id?, subject_id?}, suggestions: [{day, start_period, room_id, teacher_id?}]}`. `MISSING_SESSION` is the only "completeness" conflict (severity `warning`-class, but blocks "complete" status); the rest are hard errors that block publish.
Messages are plain teacher-friendly English with names, not IDs only, e.g. *"Dr. Sharma is already assigned to CE-A during Period 3 on Monday."*

## Engine API as built (phase 1) — `from app.engine import ...`
Tests: `cd backend; .venv\Scripts\python -m pytest` (88 tests, ~2 s). Demo: `.venv\Scripts\python scripts\demo_generate.py`. All functions are pure (inputs never mutated); models are Pydantic v2 and round-trip through JSON.

| Function | Returns |
|----------|---------|
| `generate(dataset, max_nodes=200_000, time_limit_s=10.0)` | `ScheduleResult` |
| `validate(dataset, entries, *, with_suggestions=True, max_suggestions=3, focus_entry_id=None)` | `ValidationReport` |
| `validate_move(dataset, entries, entry_id, new_day=None, new_start=None, new_room=None, new_teacher=None)` | `MoveResult` (dry run; `None` keeps the current value) |
| `validate_place(dataset, entries, session_id, day, start_period, room_id, teacher_id=None)` | `MoveResult` (place an unscheduled session) |
| `suggest_slots(dataset, entries, target, limit=5)` — `target` = Entry, Session or session id | `list[Suggestion]` (each confirmed by the validator) |
| `revalidate(dataset, entries)` | `RevalidationResult{report, needs_review:[{entry_id, codes, messages}]}`; `add_unavailability(dataset, resource_id, [(day, period)])` returns a changed *copy* of the dataset |
| `analytics(dataset, entries)` | `Analytics{teachers[periods_per_week, per_day, available_periods, utilization_pct, sessions], rooms[periods_used, available_periods, utilization_pct, per_day], batches[...]}` |
| `expand_sessions(dataset)`, `load_dataset_from_dir(path)` | `list[Session]`, `Dataset` |

`UnknownEntryError` / `UnknownSessionError` (both `ValueError`) are raised for unknown ids — map to 404.

Key shapes and semantics
- **Entry**: `{session_id, day, start_period, duration, teacher_id, room_id, subject_id, batch_id}` plus serialised `entry_id` (always equal to `session_id`; a session is placed at most once, so use it as the entry id everywhere, incl. `/entries/{entry_id}`).
- **ScheduleResult**: `{status, message, scheduled[Entry], unscheduled[{session, reasons[], reason_codes[], hints[]}], findings[str], stats{nodes, elapsed_ms, hit_limit, exhausted, max_nodes, time_limit_s, total_sessions, scheduled_count}, validation}`. (`scheduled` is the architecture's `scheduled[]`; `findings` = resource-level explanations such as "Mr. Das needs 12 sessions of 2 or more consecutive periods per week, but only 9 such blocks fit...".)
- **status**: `complete` only if everything is placed AND the independent validator reports no errors and no `MISSING_SESSION`; `partial` = at least one placed, rest listed in `unscheduled`; `failed` = nothing placed, no requirements, or (never expected) the final validation found hard errors.
- **Search limit**: if `max_nodes`/`time_limit_s` stops the search, `stats.hit_limit=true` and `message` starts with *"No complete solution found within the search limit"* and says a solution may still exist; it never claims infeasibility. The best partial found is returned and the unplaced sessions get code `SEARCH_LIMIT`.
- **Proof**: `stats.exhausted=true` means the search explored every arrangement and none places all sessions (sessions left over get `NO_FREE_SLOT`). The partial is then topped up greedily and improved by a bounded branch-and-bound; it is a good but not guaranteed-maximum partial (in ~0.5% of random tiny infeasible cases a brute-force optimum places one more session).
- **reason_codes** for unscheduled sessions: zero candidate slots — `INVALID_REFERENCE, INVALID_DURATION, NO_TEACHING_BLOCK, TEACHER_NEVER_FREE, NO_SUITABLE_ROOM, ROOM_TOO_SMALL, ROOM_NEVER_FREE`; provable shortfall by counting (incl. consecutive-block limits) — `TEACHER_OVERLOAD, BATCH_OVERLOAD, ROOM_OVERLOAD`; search — `NO_FREE_SLOT, SEARCH_LIMIT`. `hints[]` are one-line fixes for the coordinator.
- **ValidationReport**: `{valid, complete, status: valid_complete|valid_incomplete|invalid, error_count, warning_count, counts{code:n}, summary, conflicts[]}`. `valid` = no error-severity conflicts (publishable, possibly incomplete); `complete` = valid and no `MISSING_SESSION`. Conflict adds `suggested_entry_id` (the entry the `suggestions` are alternatives for). Conflicts are sorted: errors first, then day/period, code, entry ids.
- **MoveResult**: `{valid, entry (the proposed Entry), conflicts (only error conflicts involving the moved entry — problems elsewhere do not block), affected_entries (the other classes it clashes with), suggestions, message}`; `message` is the first conflict in plain English (+ "N more issues also block this change"). Overlap wording in move/place mode: *"Dr. Sharma is already assigned to CE-A during Period 3 on Monday (Data Structures)."*
- Availability rows for ids that are neither a teacher nor a room are ignored by the engine (the importer reports them). Rows with `available=1` are ignored.

## Versions & publishing
- `TimetableVersion`: `id, dataset_id, status (draft|published|archived), label, created_at, created_by, is_complete, parent_version_id, notes`.
- **Generate** always creates a NEW draft. It never mutates or replaces the published version. Edits apply only to drafts.
- **Publish**: runs validator; any hard error ⇒ 409 with report. If sessions are unscheduled ⇒ requires `acknowledge_incomplete=true`; version then has `is_complete=false` and the UI labels it "Published (incomplete)". Publishing archives the previously published version (still listed and recoverable).
- **Restore**: any version can be cloned into a new draft (`/restore`) and re-validated, then re-published.
- **Compare**: diff two versions → moved / added / removed / changed (room/teacher) entries.
- **Edit flow**: `POST .../validate-move` (dry run; returns `{valid, conflicts, affected_entries, suggestions}`) then `PATCH` applies only if valid (otherwise 422/409 with the same payload; nothing saved). A placed entry can also be unscheduled; an unscheduled session can be manually placed (same validation).
- **Availability change after generation**: updating availability on a dataset then calling revalidate on a draft/published version flags impacted entries as `needs_review` (conflict `TEACHER_UNAVAILABLE`). Published version is never silently altered; user must create a fixed draft.

## API (summary — builder writes full `docs/API.md`; paths under `/api`)
- `GET /health`
- Datasets/import: `POST /datasets/import` (multipart: files `teachers.csv, subjects.csv, batches.csv, rooms.csv, requirements.csv, days.csv, periods.csv` and optional `availability.csv`, or a single `.zip`; form fields `name, semester`) → returns dataset + **ImportReport** (per-file, per-row errors/warnings with `file,row,field,value,message,how_to_fix`); dataset is stored with `import_status: ok|has_errors`; generation is blocked (422) when errors exist. `POST /datasets/load-sample?kind=feasible|infeasible|invalid`. `GET /datasets`, `GET /datasets/{id}` (full normalized data + report), `DELETE`, `GET /templates/{name}.csv` and `GET /templates.zip` (blank CSV templates).
- Config: `PUT /datasets/{id}/config` (days, periods), `PUT /datasets/{id}/availability` (replace/patch), CRUD-light for rooms/teachers capacity if cheap.
- Generate: `POST /datasets/{id}/generate` `{max_nodes?, time_limit_s?}` → `{version, result}`.
- Versions: `GET /datasets/{id}/versions`, `GET /versions/{id}` (entries, unscheduled, validation, summary), `POST /versions/{id}/validate`, `POST /versions/{id}/publish`, `POST /versions/{id}/restore`, `GET /versions/{a}/compare/{b}`.
- Editing: `POST /versions/{id}/entries/{entry_id}/validate-move`, `PATCH /versions/{id}/entries/{entry_id}`, `POST /versions/{id}/unscheduled/{session_id}/place` (+ `validate-place`), `GET /versions/{id}/unscheduled/{session_id}/suggestions`.
- Analytics: `GET /versions/{id}/analytics` → teacher workload (periods/week, per-day), room utilization %, batch load.
- Export: `GET /versions/{id}/export.csv`, `GET /versions/{id}/export.pdf?view=batch|teacher|room&id=...` (all-in-one PDF if no id: one page per batch/teacher/room).
- Errors: JSON `{detail: {code, message, ...}}`, human-readable, never silent.

### Phase 2 as built (deviations from the summary above; **`docs/API.md` is the contract**)
- **Ids**: `dataset.id` and `version.id` are integers (SQLite autoincrement); entity ids are the CSV strings; `entry_id == session_id`.
- **Import** takes repeated multipart field `files` (identified by filename) or one `.zip`; it always answers 201 with the ImportReport and stores
  datasets with errors as `import_status: has_errors` (valid rows kept, invalid rows rejected). Generation then fails with 422 `IMPORT_HAS_ERRORS`.
  `import_status` is a property of the import and is not recomputed by later config/availability edits.
- **Availability**: `PUT /datasets/{id}/availability` takes `{rules:[{resource_id,day,period,available?}]}` (replace), `PATCH` toggles one slot, `PATCH .../availability/bulk` many.
  Only "not available" rules are stored. Also `PATCH /datasets/{id}/rooms|teachers|batches/{id}` for light edits.
- **needs_review is computed live**, never stored: `GET /versions/{id}` and `POST /versions/{id}/revalidate` (same payload as `/validate`) re-run the validator against the
  dataset as it is now, so availability / room-capacity changes flag entries (`needs_review`) without ever modifying a published version.
- **Rejected edit** = HTTP 409 `MOVE_REJECTED` whose `detail` is the error envelope plus the full MoveResult; nothing is saved. Editing, dry-running or unscheduling a
  published/archived version = 409 `VERSION_NOT_EDITABLE`. Unschedule is `POST .../entries/{id}/unschedule` (not DELETE).
- **Publish**: 409 `PUBLISH_BLOCKED` (hard conflicts, with report) / 409 `ACKNOWLEDGE_INCOMPLETE`; only drafts can be published; the old published version becomes `archived`.
  A partial unique index guarantees at most one published version per dataset.
- **Delete dataset** with a published version needs `?force=true` (409 `DATASET_HAS_PUBLISHED_VERSION` otherwise); the published version cannot be deleted directly.
- **Exports**: CSV = scheduled classes only (UTF-8 BOM, formula-safe cells); PDF = landscape A4, one page per batch / teacher / room, `view` + optional `id`.
- **Storage**: stdlib `sqlite3`, WAL, `backend/data/smartslot.db` (env `SMARTSLOT_DB` overrides), tables created if missing, multi-row writes in one `BEGIN IMMEDIATE` transaction.
  Dev reset: `POST /api/dev/reset[?sample=feasible]`, active only with env `SMARTSLOT_DEV=1`.

## Frontend pages (single-page app, left nav or top stepper)
1. **Import** — semester + name, drag-drop CSVs or "Load demo dataset (feasible / infeasible / with-errors)", download templates, **Validation summary** (counts of entities, errors table with file/row/field/how-to-fix, success state).
2. **Configure** — days, periods/times/breaks, teacher & room availability grid (click to toggle), room capacities/types, requirements overview.
3. **Generate** — big "Generate Timetable" button, loading state, result banner: ✅ Complete & valid / ⚠️ Partial (N unscheduled) / ❌ not found within search limit; stats (nodes, time).
4. **Timetable** — view switcher Batch/Teacher/Room + entity selector, weekly grid (days × periods, breaks shown), color per subject, lab/practical multi-period blocks spanning, **unscheduled panel** with reasons + suggestions, **conflict panel**, drag-and-drop or "Edit" dialog to move/change room/teacher with live pre-validation, clear rejection message with explanation and cancel; validation status badge always visible (Valid · Complete / Valid · N unscheduled / N conflicts).
5. **Publish & Versions** — version list (status chips), compare view (diff), restore, publish with incomplete-warning modal, export CSV / PDF (and print stylesheet).
6. **Insights** — teacher workload bars, room utilization, batch load (P1).
A persistent header shows dataset name/semester, current version & status.

## Quality bar
- Pytest suite for engine (feasible completes with 0 hard conflicts; infeasible reports unscheduled w/ reasons; validator catches each conflict code; determinism), importer (each error class), API (happy path + rejected edit + publish gates + published version preserved on regenerate).
- Frontend: `npm run build` must pass with no TS errors; every flow verified in a real browser.
- No fake features: nothing claims live ERP integration.
