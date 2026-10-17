# SmartSlot API reference

Everything the frontend needs to talk to the backend. Interactive docs are generated automatically at
`http://localhost:8000/docs` (Swagger UI) and `/redoc`; the machine-readable schema is `/openapi.json`.
Design decisions live in [`ARCHITECTURE.md`](ARCHITECTURE.md); this file documents the **exact JSON** the server
sends and accepts. All example responses below were copied from a real running server (long lists are shortened
and the shortening is stated).

* Base URL: `http://localhost:8000/api` (the Vite dev server proxies `/api` to it, so the UI calls `/api/...`).
* CORS is enabled for `http://localhost:5173` and `http://127.0.0.1:5173`; the `Content-Disposition` header is exposed.
* No authentication. Data comes only from imported CSV files or the bundled samples: there is no live ERP connection.

---

## 1. Conventions

| Topic | Rule |
|-------|------|
| Format | JSON (UTF-8) in and out. Uploads are `multipart/form-data`; exports are file downloads. |
| Ids | `dataset.id` and `version.id` are **integers**. Teacher / subject / batch / room ids are **strings** from the CSV (`T01`, `CE-A`, `LAB1`). |
| Entry id | `entry_id` **==** `session_id` (a string such as `CS201-CE-A-1` = subject-batch-n). A session is placed at most once, so it is the entry's id everywhere. `encodeURIComponent` it when putting it in a URL. |
| Days | Short names `Mon Tue Wed Thu Fri Sat Sun`. Requests also accept `Monday`, `mon`, ... and normalise them. |
| Periods | 1-based integers, `start`/`end` are 24-hour `"HH:MM"`. A **break is its own numbered period** with `is_break: true` (demo: periods 1,2,3, break 4, 5,6,7). Break rows are never bookable and a multi-period class never spans one. `end_period = start_period + duration - 1`. |
| Timestamps | ISO-8601 UTC, e.g. `"2026-10-16T17:52:26Z"`. |
| Ordering | Always deterministic. Datasets and versions: newest first. Entries: day order, `start_period`, `batch_id`, `session_id`. Unscheduled: requirement-file order. Dataset records: CSV file order. Conflicts: errors first, then day / period / code. |
| Names | Entries, suggestions, unscheduled items and review items carry display names (`teacher_name`, `subject_name`, `batch_name`, `room_name`, times) so the UI never has to join ids. |
| `null` vs missing | Documented fields are always present; "optional" means the value may be `null`. |

### Status codes
| Code | Meaning |
|------|---------|
| 200 / 201 / 204 | Success (201 = something was created, 204 = no body). |
| 400 | Upload could not be read (`BAD_UPLOAD`). |
| 404 | Unknown dataset, version, entry, session, template or entity. |
| 409 | The request is understood but refused because of the **current state**: rejected edit (`MOVE_REJECTED`), publish blocked, editing a non-draft, delete protection. Nothing was saved. |
| 413 | Request body too large (`REQUEST_TOO_LARGE`; multipart limit 16 MB, JSON limit 1 MB, 2 MB per CSV). |
| 422 | The **input** is not acceptable: validation errors, import errors block generation, empty dataset, invalid config. |
| 500 | Unexpected server error (`INTERNAL_ERROR`); details are only in the server log. Nothing is half-saved. |

### Error envelope (every error, no exceptions)
```json
{ "detail": { "code": "DATASET_NOT_FOUND", "message": "No dataset with id 9999 exists." } }
```
`code` is stable and machine-readable, `message` is plain English that can be shown to the user as is. Some errors add
fields next to `code`/`message` (listed per endpoint). Examples:

```json
{"detail": {"code": "DATASET_NOT_FOUND", "message": "No dataset with id 9999 exists."}}
```
```json
{
  "detail": {
    "code": "INVALID_CONFIG",
    "message": "The days/periods were not saved: '9am' is not a valid 24-hour time (HH:MM).",
    "errors": [
      {
        "field": "periods[0].start", "value": "9am",
        "message": "'9am' is not a valid 24-hour time (HH:MM)."
      }
    ]
  }
}
```

Request-body validation problems (wrong type, unknown field, ...) return **422** with `code: "VALIDATION_ERROR"` and
`errors: [{field, message}]`. Request bodies reject unknown fields, so typos are noticed.

### Error codes
| Code | HTTP | When |
|------|------|------|
| `DATASET_NOT_FOUND` `VERSION_NOT_FOUND` `ENTRY_NOT_FOUND` `SESSION_NOT_FOUND` `TEMPLATE_NOT_FOUND` `ENTITY_NOT_FOUND` `ROOM_NOT_FOUND` `TEACHER_NOT_FOUND` `BATCH_NOT_FOUND` `NOT_FOUND` | 404 | The id does not exist. |
| `IMPORT_HAS_ERRORS` | 422 | Generate on a dataset whose import has errors. Extra: `error_count`, `warning_count`. |
| `DATASET_EMPTY` | 422 | Generate on a dataset without requirements / days / teaching periods / rooms / teachers. |
| `INVALID_CONFIG` | 422 | `PUT config` problems. Extra: `errors: [{field, value, message}]`. |
| `INVALID_AVAILABILITY` | 422 | Availability rule refers to an unknown resource / day / period. Extra: `errors: [{index, field, value, message}]`. Nothing saved. |
| `NOTHING_TO_CHANGE` | 422 | A move / patch with no fields. |
| `NO_FILES` `NAME_TOO_LONG` | 422 | Import form problems. |
| `DIFFERENT_DATASETS` | 422 | Comparing versions of two datasets. |
| `VALIDATION_ERROR` | 422 | Malformed request body / query. |
| `MOVE_REJECTED` | 409 | Edit / placement would create a conflict. `detail` also contains the whole MoveResult (section 3). Nothing saved. |
| `VERSION_NOT_EDITABLE` | 409 | Editing, validating a move on, or publishing a published/archived version. Restore it to a draft first. Extra: `version_id`, `status`. |
| `PUBLISH_BLOCKED` | 409 | Hard conflicts. Extra: `validation` (a ValidationReport). |
| `ACKNOWLEDGE_INCOMPLETE` | 409 | Unscheduled sessions and `acknowledge_incomplete` not true. Extra: `unscheduled`, `total_sessions`. |
| `ALREADY_PUBLISHED` `ALREADY_SCHEDULED` `CANNOT_DELETE_PUBLISHED` `DATASET_HAS_PUBLISHED_VERSION` | 409 | See the endpoint. |
| `BAD_UPLOAD` | 400 | Unreadable multipart body, or too many files. |
| `REQUEST_TOO_LARGE` | 413 | Body over the limit. |
| `DEV_ONLY` | 404 | `POST /dev/reset` without `SMARTSLOT_DEV=1`. |
| `INTERNAL_ERROR` | 500 | Unexpected. |

---

## 2. Typical flow (what the UI calls, in order)

1. **Import**: `POST /datasets/import` (files or zip) or `POST /datasets/load-sample?kind=feasible`. Show `import_report`.
   If `can_generate` is false, show the issue table and let the user import corrected files.
2. **Configure** (optional): `GET /datasets/{id}`, then `PUT /datasets/{id}/config`, `PATCH .../availability`, `PATCH .../rooms/{id}`.
3. **Generate**: `POST /datasets/{id}/generate` -> `{version, result}`. Show `result.status`: `complete`, `partial`
   (`version.unscheduled` lists the rest with reasons) or `failed`.
4. **Review**: the response `version` is already the full detail; reload any time with `GET /versions/{id}`.
5. **Edit** (drafts only): `POST .../entries/{entry_id}/validate-move` while the user drags, then `PATCH .../entries/{entry_id}`.
   A rejected `PATCH` (409) changed nothing and explains why. Unscheduled sessions: `.../unscheduled/{session_id}/suggestions`, `place`.
6. **Publish**: `POST /versions/{id}/publish` (add `{"acknowledge_incomplete": true}` after the user confirmed the warning).
7. **Export**: `GET /versions/{id}/export.csv` and `/export.pdf?view=batch|teacher|room[&id=...]`.
8. **Revise**: `POST /versions/{id}/restore` makes an editable draft copy of any version; `GET /versions/{a}/compare/{b}` shows what changed.

---

## 3. Data shapes (TypeScript)

```ts
type Day = "Mon" | "Tue" | "Wed" | "Thu" | "Fri" | "Sat" | "Sun";
type VersionStatus = "draft" | "published" | "archived";
type ValidationStatus = "valid_complete" | "valid_incomplete" | "invalid";

interface ApiError { detail: { code: string; message: string; [extra: string]: unknown } }

// ---------- records (engine models, exactly as in the CSV) ----------
interface Teacher     { teacher_id: string; name: string; department_id: string }
interface Subject     { subject_id: string; name: string; department_id: string; session_type: "lecture" | "practical" }
interface Batch       { batch_id: string; name: string; semester: string; student_count: number; department_id: string }
interface Room        { room_id: string; name: string; capacity: number; room_type: "classroom" | "lab" }
interface Requirement { subject_id: string; batch_id: string; teacher_id: string; sessions_per_week: number; duration: number }
interface PeriodDef   { period: number; start: string; end: string; is_break: boolean }
interface AvailabilityRule { resource_id: string; day: Day; period: number; available: false } // only "not available" rules exist

// ---------- import ----------
interface ImportIssue {
  severity: "error" | "warning";
  file: string | null;       // "requirements.csv"; null only for whole-upload problems
  row: number | null;        // spreadsheet row, header = row 1; null for whole-file problems
  field: string | null;      // column name ("teacher_id") or "subject_id + batch_id + teacher_id"
  value: string | null;      // offending cell text ("" when empty)
  code: string;              // stable, see section 6
  message: string;           // plain English
  how_to_fix: string;
}
interface FileSummary {
  file: string; key: string; required: boolean;
  present: boolean;          // a file with this name was supplied
  rows: number; accepted: number; rejected: number; errors: number; warnings: number;
}
interface ImportReport {
  status: "ok" | "has_errors";
  error_count: number; warning_count: number;
  total_sessions: number;                  // weekly sessions the accepted requirements expand into
  counts: Record<string, number>;          // accepted records per file key
  files: FileSummary[];                    // always the 8 files, README order
  issues: ImportIssue[];                   // sorted: file order, row, errors before warnings
  truncated: boolean;                      // true if more than 200 issues/file were found (counts stay exact)
}

// ---------- datasets ----------
interface DatasetSummary {
  id: number; name: string; semester: string;
  source: string;                          // "upload" | "sample:feasible" | ...
  import_status: "ok" | "has_errors";
  created_at: string; updated_at: string;
  counts: Record<string, number>;          // live counts: teachers, subjects, batches, rooms, requirements, days, periods, availability
  error_count: number; warning_count: number;   // from the import
  total_sessions: number; version_count: number;
  published_version_id: number | null;
}
interface DatasetDetail extends DatasetSummary {
  import_report: ImportReport;
  teachers: Teacher[]; subjects: Subject[]; batches: Batch[]; rooms: Room[]; requirements: Requirement[];
  days: Day[]; periods: PeriodDef[]; teaching_periods: number[];   // non-break period numbers
  availability: AvailabilityRule[];
}
interface ImportResponse { dataset: DatasetSummary; import_report: ImportReport; can_generate: boolean }
interface DatasetEditResponse { dataset: DatasetDetail; warnings: string[] }

// ---------- timetable ----------
interface Entry {                          // one scheduled class
  entry_id: string; session_id: string;    // identical
  day: Day; start_period: number; end_period: number; duration: number;
  start_time: string | null; end_time: string | null;       // "09:00", "10:40" (start of first / end of last period)
  subject_id: string; subject_name: string; subject_type: "lecture" | "practical";
  batch_id: string;   batch_name: string;
  teacher_id: string; teacher_name: string;
  room_id: string;    room_name: string; room_type: "classroom" | "lab" | "";
  needs_review: boolean;                   // clashes with the CURRENT availability / room data
  review_messages: string[];
}
interface Suggestion {                     // an alternative placement, already confirmed by the validator
  day: Day; start_period: number; end_period: number; duration: number;
  start_time: string | null; end_time: string | null;
  room_id: string; room_name: string;
  teacher_id: string | null; teacher_name: string | null;
  label: string;                           // "Tuesday Period 3 in Room 102"
}
interface Conflict {
  code: "TEACHER_OVERLAP" | "ROOM_OVERLAP" | "BATCH_OVERLAP" | "TEACHER_UNAVAILABLE" | "ROOM_UNAVAILABLE"
      | "ROOM_CAPACITY" | "ROOM_TYPE" | "INVALID_DURATION" | "OUTSIDE_WORKING_HOURS" | "BLOCKED_PERIOD"
      | "INVALID_REFERENCE" | "MISSING_SESSION";
  severity: "error" | "warning";           // MISSING_SESSION is the only "warning"
  message: string;                         // "Dr. Sharma is already assigned to CE-A during Period 5 on Monday (Data Structures)."
  day: Day | null; period: number | null;
  entry_ids: string[];                     // the classes involved
  involved: { teacher_id: string | null; room_id: string | null; batch_id: string | null; subject_id: string | null };
  suggestions: Suggestion[];               // alternatives for `suggested_entry_id` (empty inside a MoveResult: see there)
  suggested_entry_id: string | null;
}
interface ValidationReport {
  valid: boolean;                          // no error-severity conflicts: safe to publish (maybe incomplete)
  complete: boolean;                       // valid AND every required session scheduled
  status: ValidationStatus;
  error_count: number; warning_count: number;
  counts: Record<string, number>;          // conflicts per code
  summary: string;
  conflicts: Conflict[];
}
interface UnscheduledItem {
  session_id: string; subject_id: string; subject_name: string; subject_type: string;
  batch_id: string; batch_name: string; teacher_id: string; teacher_name: string;
  duration: number; index: number; of: number;     // "session `index` of `of`" for this subject + batch
  reasons: string[];                       // plain English, why it could not be placed
  reason_codes: string[];                  // see section 6
  hints: string[];                         // one-line fixes for the coordinator
}
interface ReviewItem { entry_id: string; label: string; codes: string[]; messages: string[] }

interface Summary {
  total_sessions: number; scheduled: number; unscheduled: number;
  status: ValidationStatus;                // drives the always-visible badge
  error_count: number; warning_count: number; needs_review_count: number;
  message: string;                         // one sentence for the badge tooltip
}
interface VersionMeta {
  id: number; dataset_id: number; seq: number;
  status: VersionStatus;
  status_label: "Draft" | "Published" | "Published (incomplete)" | "Archived";   // show this text
  label: string; source: "generated" | "restored";
  created_at: string; created_by: string; published_at: string | null;
  is_complete: boolean;                    // every required session is scheduled (fixed at publish time for published versions)
  parent_version_id: number | null; notes: string;
  summary: Summary;
}
interface SearchStats { nodes: number; elapsed_ms: number; hit_limit: boolean; exhausted: boolean;
                        max_nodes: number; time_limit_s: number; total_sessions: number; scheduled_count: number }
interface GenerationResult {
  status: "complete" | "partial" | "failed";
  message: string;                         // starts with "No complete solution found within the search limit" if stats.hit_limit
  findings: string[];                      // resource-level explanations
  stats: SearchStats;
}
interface VersionDetail extends VersionMeta {
  entries: Entry[];
  unscheduled: UnscheduledItem[];
  validation: ValidationReport;            // recomputed live against the dataset as it is NOW
  needs_review: ReviewItem[];
  dataset: { id: number; name: string; semester: string; days: Day[]; periods: PeriodDef[] };   // enough to draw the grid
  generation: GenerationResult | null;     // null for restored versions
}

// ---------- editing ----------
interface MoveResult {                     // dry-run result AND the body of a MOVE_REJECTED error
  valid: boolean;
  message: string;                         // first problem in plain English (+ "N more issues also block this change.")
  entry: Entry | null;                     // the proposed placement (what the class would become)
  conflicts: Conflict[];                   // only conflicts that involve this class; conflict.suggestions is [] here
  affected_entries: Entry[];               // the other classes it would clash with
  suggestions: Suggestion[];               // valid alternatives (use these)
}
interface EditResponse { message: string; entry: Entry | null; version: VersionDetail }

// ---------- other ----------
interface ValidateResponse { version_id: number; summary: Summary; validation: ValidationReport; needs_review: ReviewItem[] }
interface PublishResponse { version: VersionDetail; archived_version_id: number | null; message: string }
interface RestoreResponse { version: VersionDetail; message: string }
interface GenerateResponse { version: VersionDetail; result: GenerationResult }

interface Change {
  type: "added" | "removed" | "moved" | "room_changed" | "teacher_changed" | "changed";   // "changed" = more than one aspect
  aspects: ("moved" | "room_changed" | "teacher_changed")[];
  session_id: string; subject_id: string; subject_name: string; batch_id: string; batch_name: string;
  text: string;                            // "CS201 for CE-A moved Mon P1 → Tue P3"
  before: Entry | null; after: Entry | null;
}
interface CompareResult {
  from_version: { id: number; label: string; status: VersionStatus; status_label: string };
  to_version:   { id: number; label: string; status: VersionStatus; status_label: string };
  summary: { added: number; removed: number; moved: number; room_changed: number; teacher_changed: number; unchanged: number; changed_total: number };
  changes: Change[];                       // sorted: modified, added, removed; then by session_id
}
interface Analytics {
  version_id: number;
  teachers: { teacher_id: string; name: string; sessions: number; periods_per_week: number; per_day: Record<Day, number>; available_periods: number; utilization_pct: number }[];
  rooms:    { room_id: string; name: string; room_type: string; periods_used: number; available_periods: number; utilization_pct: number; per_day: Record<Day, number> }[];
  batches:  { batch_id: string; name: string; sessions: number; periods_per_week: number; per_day: Record<Day, number>; teaching_periods: number; utilization_pct: number }[];
  total_periods_scheduled: number; teaching_periods_per_week: number;
}
```

**Status badge recipe** (always visible): `summary.status` -> `valid_complete` green "Valid - Complete",
`valid_incomplete` amber "Valid - N unscheduled" (`summary.unscheduled`), `invalid` red "N conflicts" (`summary.error_count`).
Show `status_label` for the version chip.

**Grid recipe**: columns = `version.dataset.days`; rows = `version.dataset.periods` (draw `is_break` rows shaded and empty);
place an entry at `(day, start_period)` and span it over `duration` rows. Batch / teacher / room views are simply
`entries.filter(e => e.batch_id === id)` etc.; no extra request is needed.

---

## 4. Endpoints

### 4.1 System

#### `GET /api/health`
```json
{
  "status": "ok", "service": "smartslot-api", "version": "0.2.0", "dev_mode": true,
  "database": "smartslot.db"
}
```

#### `POST /api/dev/reset`  (development only)
Wipes the whole database. `?sample=feasible|infeasible|invalid` loads that sample afterwards. Returns
`{reset: true, dataset: DatasetSummary | null}`. Works only if the server was started with `SMARTSLOT_DEV=1`
(`start.ps1` does that); otherwise **404 `DEV_ONLY`** and nothing is touched. After a reset ids start again at 1.
```json
{
  "reset": true,
  "dataset": {
    "id": 1, "name": "Demo - CE Semester 3 (complete timetable)", "semester": "3",
    "source": "sample:feasible", "import_status": "ok", "created_at": "2026-10-16T17:52:51Z",
    "updated_at": "2026-10-16T17:52:51Z", "error_count": 0, "warning_count": 0, "total_sessions": 60,
    "version_count": 0, "published_version_id": null
  }
}
```

### 4.2 Import and datasets

#### `POST /api/datasets/import`
`multipart/form-data`:

| Field | Type | Notes |
|-------|------|-------|
| `files` | file, repeatable | Each CSV, identified by **its own filename** (`teachers.csv`, `subjects.csv`, `batches.csv`, `rooms.csv`, `requirements.csv`, `days.csv`, `periods.csv`, optional `availability.csv`). Or send a **single `.zip`** containing them. A field named after the file (`teachers`, `teachers.csv`) also works. |
| `name` | text | Dataset name (max 120). Default `Imported dataset`. |
| `semester` | text | Optional (max 40). If blank, the first batch's `semester` is used. |

Always answers **201** with `ImportResponse`, even when the CSVs contain errors: the dataset is stored with
`import_status: "has_errors"` and the report says exactly what is wrong. **Valid rows are kept, invalid rows are
rejected (never repaired, never silently dropped), and generation is blocked** (`POST .../generate` -> 422
`IMPORT_HAS_ERRORS`) until corrected files are imported again (import creates a new dataset; delete the old one).

Security/limits: 2 MB per CSV, 24 files per request, 16 MB per request, UTF-8 only (BOM accepted), at most
20 000 data rows per file, zip: 40 members / 12 MB expanded, member names are never used as paths (path-like names
are skipped with a warning), only `.csv` and `.zip` are read.

Successful import (`import_report.files`, which has one summary object per CSV file, is omitted here):
```json
{
  "dataset": {
    "id": 2,
    "name": "Demo - CE Semester 3 (complete timetable)",
    "semester": "3",
    "source": "sample:feasible",
    "import_status": "ok",
    "created_at": "2026-10-16T17:52:26Z",
    "updated_at": "2026-10-16T17:52:26Z",
    "counts": {
      "teachers": 6, "subjects": 5, "batches": 3, "rooms": 4, "requirements": 15, "days": 5,
      "periods": 7, "availability": 13
    },
    "error_count": 0,
    "warning_count": 0,
    "total_sessions": 60,
    "version_count": 0,
    "published_version_id": null
  },
  "import_report": {
    "status": "ok",
    "error_count": 0,
    "warning_count": 0,
    "total_sessions": 60,
    "counts": {
      "teachers": 6, "subjects": 5, "batches": 3, "rooms": 4, "requirements": 15, "days": 5,
      "periods": 7, "availability": 13
    },
    "issues": [],
    "truncated": false
  },
  "can_generate": true
}
```

Import with errors (`invalid` sample; only the first 3 of 36 issues and 3 of 8 file summaries shown):
```json
{
  "dataset": {
    "id": 1,
    "name": "Demo - CE Semester 3 (CSV with errors)",
    "semester": "3",
    "source": "sample:invalid",
    "import_status": "has_errors",
    "created_at": "2026-10-16T17:52:26Z",
    "updated_at": "2026-10-16T17:52:26Z",
    "counts": {
      "teachers": 4, "subjects": 4, "batches": 2, "rooms": 3, "requirements": 4, "days": 5,
      "periods": 7, "availability": 3
    },
    "error_count": 35,
    "warning_count": 1,
    "total_sessions": 16,
    "version_count": 0,
    "published_version_id": null
  },
  "import_report": {
    "status": "has_errors",
    "error_count": 35,
    "warning_count": 1,
    "total_sessions": 16,
    "counts": {
      "teachers": 4, "subjects": 4, "batches": 2, "rooms": 3, "requirements": 4, "days": 5,
      "periods": 7, "availability": 3
    },
    "files": [
      {
        "file": "teachers.csv", "key": "teachers", "required": true, "present": true, "rows": 7,
        "accepted": 4, "rejected": 3, "errors": 3, "warnings": 0
      },
      {
        "file": "subjects.csv", "key": "subjects", "required": true, "present": true, "rows": 6,
        "accepted": 4, "rejected": 2, "errors": 2, "warnings": 0
      },
      {
        "file": "batches.csv", "key": "batches", "required": true, "present": true, "rows": 6,
        "accepted": 2, "rejected": 4, "errors": 4, "warnings": 1
      }
    ],
    "issues": [
      {
        "severity": "error", "file": "teachers.csv", "row": 6, "field": "teacher_id", "value": "T03",
        "code": "DUPLICATE_ID", "message": "teacher_id 'T03' is already used in row 4 (Dr. Mehta).",
        "how_to_fix": "Give this teacher a unique teacher_id, or delete the row if it is a repeat. The first row keeps the id."
      },
      {
        "severity": "error", "file": "teachers.csv", "row": 7, "field": "name", "value": "",
        "code": "MISSING_FIELD", "message": "name is empty, but it is required.",
        "how_to_fix": "Fill in the teacher's name."
      },
      {
        "severity": "error", "file": "teachers.csv", "row": 8, "field": "teacher_id", "value": "",
        "code": "MISSING_FIELD", "message": "teacher_id is empty, but it is required.",
        "how_to_fix": "Fill in teacher_id for this teacher."
      }
    ],
    "truncated": false
  },
  "can_generate": false
}
```

Import issue `code`s are listed in section 6. `row` is the spreadsheet row (header = row 1).

#### `POST /api/datasets/load-sample?kind=feasible|infeasible|invalid`
Reads `sample_data/<kind>/` **through the same importer** and returns the same `ImportResponse` (201).
`feasible`: 60/60 sessions, `infeasible`: DS Lab 4x/week -> 63/66, `invalid`: 35 deliberate errors. Optional `name` query.

#### `GET /api/datasets` -> `DatasetSummary[]`
Newest first.
```json
[
  {
    "id": 2,
    "name": "Demo - CE Semester 3 (complete timetable)",
    "semester": "3",
    "source": "sample:feasible",
    "import_status": "ok",
    "created_at": "2026-10-16T17:52:26Z",
    "updated_at": "2026-10-16T17:52:26Z",
    "counts": {
      "teachers": 6, "subjects": 5, "batches": 3, "rooms": 4, "requirements": 15, "days": 5,
      "periods": 7, "availability": 13
    },
    "error_count": 0,
    "warning_count": 0,
    "total_sessions": 60,
    "version_count": 0,
    "published_version_id": null
  },
  {
    "id": 1,
    "name": "Demo - CE Semester 3 (CSV with errors)",
    "semester": "3",
    "source": "sample:invalid",
    "import_status": "has_errors",
    "created_at": "2026-10-16T17:52:26Z",
    "updated_at": "2026-10-16T17:52:26Z",
    "counts": {
      "teachers": 4, "subjects": 4, "batches": 2, "rooms": 3, "requirements": 4, "days": 5,
      "periods": 7, "availability": 3
    },
    "error_count": 35,
    "warning_count": 1,
    "total_sessions": 16,
    "version_count": 0,
    "published_version_id": null
  }
]
```

#### `GET /api/datasets/{id}` -> `DatasetDetail`
All normalised records plus the import report (lists shortened to 2 items here; `import_report.files` omitted).
```json
{
  "id": 2,
  "name": "Demo - CE Semester 3 (complete timetable)",
  "semester": "3",
  "source": "sample:feasible",
  "import_status": "ok",
  "created_at": "2026-10-16T17:52:26Z",
  "updated_at": "2026-10-16T17:52:26Z",
  "counts": {
    "teachers": 6, "subjects": 5, "batches": 3, "rooms": 4, "requirements": 15, "days": 5,
    "periods": 7, "availability": 13
  },
  "error_count": 0,
  "warning_count": 0,
  "total_sessions": 60,
  "version_count": 0,
  "published_version_id": null,
  "import_report": {
    "status": "ok",
    "error_count": 0,
    "warning_count": 0,
    "total_sessions": 60,
    "counts": {
      "teachers": 6, "subjects": 5, "batches": 3, "rooms": 4, "requirements": 15, "days": 5,
      "periods": 7, "availability": 13
    },
    "issues": [],
    "truncated": false
  },
  "teachers": [
    {"teacher_id": "T01", "name": "Dr. Sharma", "department_id": "CE"},
    {"teacher_id": "T02", "name": "Prof. Iyer", "department_id": "CE"}
  ],
  "subjects": [
    {
      "subject_id": "CS201", "name": "Data Structures", "department_id": "CE",
      "session_type": "lecture"
    },
    {"subject_id": "CS202", "name": "DBMS", "department_id": "CE", "session_type": "lecture"}
  ],
  "batches": [
    {
      "batch_id": "CE-A", "name": "CE-A", "semester": "3", "student_count": 60,
      "department_id": "CE"
    },
    {
      "batch_id": "CE-B", "name": "CE-B", "semester": "3", "student_count": 55,
      "department_id": "CE"
    }
  ],
  "rooms": [
    {"room_id": "R101", "name": "Room 101", "capacity": 65, "room_type": "classroom"},
    {"room_id": "R102", "name": "Room 102", "capacity": 58, "room_type": "classroom"}
  ],
  "requirements": [
    {
      "subject_id": "CS201", "batch_id": "CE-A", "teacher_id": "T01", "sessions_per_week": 5,
      "duration": 1
    },
    {
      "subject_id": "CS201", "batch_id": "CE-B", "teacher_id": "T01", "sessions_per_week": 5,
      "duration": 1
    }
  ],
  "days": ["Mon", "Tue"],
  "periods": [
    {"period": 1, "start": "09:00", "end": "09:50", "is_break": false},
    {"period": 2, "start": "09:50", "end": "10:40", "is_break": false}
  ],
  "teaching_periods": [1, 2],
  "availability": [
    {"resource_id": "LAB1", "day": "Wed", "period": 5, "available": false},
    {"resource_id": "LAB1", "day": "Wed", "period": 6, "available": false}
  ]
}
```

#### `DELETE /api/datasets/{id}` -> 204
Deletes the dataset with all its versions. If it has a **published** version the server answers **409
`DATASET_HAS_PUBLISHED_VERSION`** (extra: `published_version_id`) unless you add `?force=true`.
```json
{
  "detail": {
    "code": "DATASET_HAS_PUBLISHED_VERSION",
    "message": "'Demo - CE Semester 3 (complete timetable)' has a published timetable (First run). Deleting the dataset would delete it too. Send ?force=true to delete everything.",
    "published_version_id": 1
  }
}
```

#### Templates
* `GET /api/templates` -> `string[]` (`["teachers","subjects",...,"availability"]`)
* `GET /api/templates/{name}.csv` -> header-only CSV download, e.g. `teachers.csv` = `teacher_id,name,department_id`
* `GET /api/templates.zip` -> all eight blank templates

### 4.3 Configuration and availability

#### `PUT /api/datasets/{id}/config` -> `DatasetEditResponse`
Replaces working days and the period grid.
```json
{ "days": ["Mon","Tue","Wed","Thu","Fri","Sat"],
  "periods": [ {"period":1,"start":"09:00","end":"09:50"},
               {"period":4,"start":"11:30","end":"12:20","is_break":true} ] }
```
`days` accept long names; times may be `9:00` (normalised to `09:00`); at least one non-break period is required.
Problems -> 422 `INVALID_CONFIG` with `errors`; nothing saved. `warnings` mentions availability rules for removed days
or periods and that existing versions were made with the old grid (their validation is recomputed live).
```json
{
  "dataset": {
    "id": 3,
    "name": "Demo - CE Semester 3 (impossible lab requirement)",
    "semester": "3",
    "source": "sample:infeasible",
    "import_status": "ok",
    "created_at": "2026-10-16T17:52:27Z",
    "updated_at": "2026-10-16T17:52:51Z",
    "error_count": 0,
    "warning_count": 0,
    "total_sessions": 66,
    "version_count": 1,
    "published_version_id": 4,
    "days": ["Mon", "Tue"],
    "periods": [
      {"period": 1, "start": "09:00", "end": "09:50", "is_break": false},
      {"period": 2, "start": "09:50", "end": "10:40", "is_break": false}
    ],
    "teaching_periods": [1, 2]
  },
  "warnings": ["4 availability rule(s) refer to days or periods that no longer exist; they have no effect.", "Existing timetable versions were made with the old days/periods. Open them and check their validation, or generate a new version."]
}
```

#### Availability
Only **unavailable** slots are stored (the default is available). `resource_id` is a teacher id or room id.
Rules for unknown resources / days not in the dataset / unknown periods are rejected with 422
`INVALID_AVAILABILITY` and **nothing is saved**. A rule on a break period is accepted with a warning (it has no effect).
All three return `DatasetEditResponse` (`dataset.availability` is the new full list).

* `PUT /api/datasets/{id}/availability` - replace the whole list: `{"rules":[{"resource_id":"T05","day":"Wed","period":5}, {"resource_id":"LAB1","day":"Wed","period":5,"available":false}]}`
  (`available` defaults to `false`; `true` rules are accepted and ignored). `{"rules":[]}` clears everything.
* `PATCH /api/datasets/{id}/availability` - toggle **one** slot: `{"resource_id":"T02","day":"Mon","period":2,"available":false}`
  marks it unavailable, `"available":true` removes the rule. Idempotent.
* `PATCH /api/datasets/{id}/availability/bulk` - `{"changes":[ ...same objects... ]}` (max 2000), all or nothing.

After changing availability, call `POST /versions/{id}/revalidate` (or just `GET /versions/{id}`) to see which classes need review.
```json
{
  "dataset": {
    "id": 3,
    "name": "Demo - CE Semester 3 (impossible lab requirement)",
    "semester": "3",
    "source": "sample:infeasible",
    "import_status": "ok",
    "created_at": "2026-10-16T17:52:27Z",
    "updated_at": "2026-10-16T17:52:51Z",
    "error_count": 0,
    "warning_count": 0,
    "total_sessions": 66,
    "version_count": 1,
    "published_version_id": 4,
    "days": ["Mon", "Tue"],
    "teaching_periods": [1, 2],
    "availability": [
      {"resource_id": "LAB1", "day": "Wed", "period": 5, "available": false},
      {"resource_id": "T05", "day": "Wed", "period": 5, "available": false}
    ]
  },
  "warnings": []
}
```

#### Light editing: `PATCH /api/datasets/{id}/rooms/{room_id}` | `.../teachers/{teacher_id}` | `.../batches/{batch_id}`
Send any of: rooms `{name, capacity, room_type}`, teachers `{name, department_id}`, batches `{name, student_count, semester, department_id}`
(same validation as the CSV: capacity / student_count 1..10000, `room_type` `classroom|lab`). Empty body -> 422 `NOTHING_TO_CHANGE`;
unknown id -> 404. Returns `DatasetEditResponse`. Existing versions are **not** modified; their live validation
reflects the change (for example `ROOM_CAPACITY` entries appear in `needs_review`).

### 4.4 Generate and versions

#### `POST /api/datasets/{id}/generate` -> 201 `GenerateResponse`
Body (optional): `{ "max_nodes"?: number, "time_limit_s"?: number, "label"?: string, "notes"?: string, "created_by"?: string }`
(`created_by` defaults to `"coordinator"`, `label` to `"Version N"`). **Always creates a NEW draft**; the published version
is never touched. 201 is returned for `complete`, `partial` and `failed` alike - read `result.status`.
Blocked with **422 `IMPORT_HAS_ERRORS`** (dataset import has errors) or **422 `DATASET_EMPTY`**; nothing is created.

`result.status`: `complete` (every session placed, 0 conflicts), `partial` (see `version.unscheduled`), `failed`.
If the search limit stopped the search, `stats.hit_limit` is true and `message` starts with
*"No complete solution found within the search limit"* - it is never presented as proof that no solution exists.

Feasible sample (every list is cut to its first 2 items here; the real response has 60 `entries` and 7 `periods`):
```json
{
  "version": {
    "id": 1,
    "dataset_id": 2,
    "seq": 1,
    "status": "draft",
    "status_label": "Draft",
    "label": "First run",
    "source": "generated",
    "created_at": "2026-10-16T17:52:26Z",
    "created_by": "coordinator",
    "published_at": null,
    "is_complete": true,
    "parent_version_id": null,
    "notes": "",
    "summary": {
      "total_sessions": 60, "scheduled": 60, "unscheduled": 0, "status": "valid_complete",
      "error_count": 0, "warning_count": 0, "needs_review_count": 0,
      "message": "Valid and complete: all 60 required sessions are scheduled with no conflicts."
    },
    "entries": [
      {
        "entry_id": "CS291-CE-A-1", "session_id": "CS291-CE-A-1", "day": "Mon", "start_period": 1,
        "end_period": 2, "duration": 2, "start_time": "09:00", "end_time": "10:40",
        "subject_id": "CS291", "subject_name": "DS Lab", "subject_type": "practical",
        "batch_id": "CE-A", "batch_name": "CE-A", "teacher_id": "T05", "teacher_name": "Mr. Das",
        "room_id": "LAB1", "room_name": "Computer Lab 1", "room_type": "lab", "needs_review": false,
        "review_messages": []
      },
      {
        "entry_id": "CS202-CE-B-1", "session_id": "CS202-CE-B-1", "day": "Mon", "start_period": 1,
        "end_period": 1, "duration": 1, "start_time": "09:00", "end_time": "09:50",
        "subject_id": "CS202", "subject_name": "DBMS", "subject_type": "lecture", "batch_id": "CE-B",
        "batch_name": "CE-B", "teacher_id": "T03", "teacher_name": "Dr. Mehta", "room_id": "R102",
        "room_name": "Room 102", "room_type": "classroom", "needs_review": false,
        "review_messages": []
      }
    ],
    "unscheduled": [],
    "validation": {
      "valid": true, "complete": true, "status": "valid_complete", "error_count": 0,
      "warning_count": 0, "counts": {},
      "summary": "Valid and complete: all 60 required sessions are scheduled with no conflicts.",
      "conflicts": []
    },
    "needs_review": [],
    "dataset": {
      "id": 2,
      "name": "Demo - CE Semester 3 (complete timetable)",
      "semester": "3",
      "days": ["Mon", "Tue"],
      "periods": [
        {"period": 1, "start": "09:00", "end": "09:50", "is_break": false},
        {"period": 2, "start": "09:50", "end": "10:40", "is_break": false}
      ]
    },
    "generation": {
      "status": "complete",
      "message": "Timetable generated: all 60 sessions are scheduled with no conflicts.",
      "findings": [],
      "stats": {
        "nodes": 60, "elapsed_ms": 13, "hit_limit": false, "exhausted": false, "max_nodes": 200000,
        "time_limit_s": 10.0, "total_sessions": 60, "scheduled_count": 60
      }
    }
  },
  "result": {
    "status": "complete",
    "message": "Timetable generated: all 60 sessions are scheduled with no conflicts.",
    "findings": [],
    "stats": {
      "nodes": 60, "elapsed_ms": 13, "hit_limit": false, "exhausted": false, "max_nodes": 200000,
      "time_limit_s": 10.0, "total_sessions": 60, "scheduled_count": 60
    }
  }
}
```
Infeasible sample - `partial` with explanations (entries omitted, 1 of 3 unscheduled items shown):
```json
{
  "version": {
    "id": 4,
    "dataset_id": 3,
    "seq": 1,
    "status": "draft",
    "status_label": "Draft",
    "label": "Version 1",
    "source": "generated",
    "created_at": "2026-10-16T17:52:27Z",
    "created_by": "coordinator",
    "published_at": null,
    "is_complete": false,
    "parent_version_id": null,
    "notes": "",
    "summary": {
      "total_sessions": 66, "scheduled": 63, "unscheduled": 3, "status": "valid_incomplete",
      "error_count": 0, "warning_count": 3, "needs_review_count": 0,
      "message": "No conflicts, but 3 of 66 required session(s) are not scheduled yet."
    },
    "unscheduled": [
      {
        "session_id": "CS291-CE-A-4",
        "subject_id": "CS291",
        "subject_name": "DS Lab",
        "subject_type": "practical",
        "batch_id": "CE-A",
        "batch_name": "CE-A",
        "teacher_id": "T05",
        "teacher_name": "Mr. Das",
        "duration": 2,
        "index": 4,
        "of": 4,
        "reasons": ["Mr. Das needs 12 sessions of 2 or more consecutive periods per week, but only 9 such blocks fit in the periods Mr. Das is available."],
        "reason_codes": ["ROOM_OVERLOAD"],
        "hints": ["Reduce Mr. Das's sessions per week, open up more availability, or give some classes to another teacher."]
      }
    ],
    "needs_review": [],
    "generation": {
      "status": "partial",
      "message": "Partial timetable: 63 of 66 sessions scheduled. 3 sessions cannot be scheduled with the current data (see the reasons for each).",
      "findings": ["Mr. Das needs 12 sessions of 2 or more consecutive periods per week, but only 9 such blocks fit in the periods Mr. Das is available."],
      "stats": {
        "nodes": 63, "elapsed_ms": 13, "hit_limit": false, "exhausted": false, "max_nodes": 200000,
        "time_limit_s": 10.0, "total_sessions": 66, "scheduled_count": 63
      }
    }
  },
  "result": {
    "status": "partial",
    "message": "Partial timetable: 63 of 66 sessions scheduled. 3 sessions cannot be scheduled with the current data (see the reasons for each).",
    "findings": ["Mr. Das needs 12 sessions of 2 or more consecutive periods per week, but only 9 such blocks fit in the periods Mr. Das is available."],
    "stats": {
      "nodes": 63, "elapsed_ms": 13, "hit_limit": false, "exhausted": false, "max_nodes": 200000,
      "time_limit_s": 10.0, "total_sessions": 66, "scheduled_count": 63
    }
  }
}
```
Blocked (`invalid` sample):
```json
{
  "detail": {
    "code": "IMPORT_HAS_ERRORS",
    "message": "This dataset has 35 import error(s), so a timetable cannot be generated yet. Fix the CSV files and import them again. First problems: teachers.csv row 6: teacher_id 'T03' is already used in row 4 (Dr. Mehta).; teachers.csv row 7: name is empty, but it is required.; teachers.csv row 8: teacher_id is empty, but it is required.",
    "error_count": 35, "warning_count": 1
  }
}
```

#### `GET /api/datasets/{id}/versions` -> `VersionMeta[]`
Newest first. Light: no entries (but `summary` is computed live).
```json
[
  {
    "id": 2,
    "dataset_id": 2,
    "seq": 2,
    "status": "draft",
    "status_label": "Draft",
    "label": "Version 2",
    "source": "generated",
    "created_at": "2026-10-16T17:52:26Z",
    "created_by": "coordinator",
    "published_at": null,
    "is_complete": true,
    "parent_version_id": null,
    "notes": "",
    "summary": {
      "total_sessions": 60, "scheduled": 60, "unscheduled": 0, "status": "valid_complete",
      "error_count": 0, "warning_count": 0, "needs_review_count": 0,
      "message": "Valid and complete: all 60 required sessions are scheduled with no conflicts."
    }
  },
  {
    "id": 1,
    "dataset_id": 2,
    "seq": 1,
    "status": "published",
    "status_label": "Published",
    "label": "First run",
    "source": "generated",
    "created_at": "2026-10-16T17:52:26Z",
    "created_by": "coordinator",
    "published_at": "2026-10-16T17:52:26Z",
    "is_complete": true,
    "parent_version_id": null,
    "notes": "",
    "summary": {
      "total_sessions": 60, "scheduled": 60, "unscheduled": 0, "status": "valid_complete",
      "error_count": 0, "warning_count": 0, "needs_review_count": 0,
      "message": "Valid and complete: all 60 required sessions are scheduled with no conflicts."
    }
  }
]
```

#### `GET /api/versions/{id}` -> `VersionDetail`
The full picture (see the generate example above for the shape). `validation` and `needs_review` are recomputed
on every call from the stored entries against the dataset as it is **now**, so a published version affected by a later
availability change shows `summary.status: "invalid"` and `needs_review` entries - while its own `status`
stays `published` and its entries are never changed.

#### `POST /api/versions/{id}/validate` -> `ValidateResponse`
Re-runs the independent validator.
```json
{
  "version_id": 1,
  "summary": {
    "total_sessions": 60, "scheduled": 60, "unscheduled": 0, "status": "valid_complete",
    "error_count": 0, "warning_count": 0, "needs_review_count": 0,
    "message": "Valid and complete: all 60 required sessions are scheduled with no conflicts."
  },
  "validation": {
    "valid": true, "complete": true, "status": "valid_complete", "error_count": 0,
    "warning_count": 0, "counts": {},
    "summary": "Valid and complete: all 60 required sessions are scheduled with no conflicts.",
    "conflicts": []
  },
  "needs_review": []
}
```

#### `POST /api/versions/{id}/revalidate` -> `ValidateResponse`
Same payload; use it after availability or room edits. Flags impacted entries in `needs_review`
(also set as `needs_review: true` on the entries of `GET /versions/{id}`) and **never modifies the version**.
Example after Prof. Iyer was marked unavailable in a slot that a published class uses:
```json
{
  "version_id": 1,
  "summary": {
    "total_sessions": 60, "scheduled": 60, "unscheduled": 0, "status": "invalid", "error_count": 1,
    "warning_count": 0, "needs_review_count": 1,
    "message": "1 conflict must be fixed before this timetable can be published (teacher not available: 1)."
  },
  "validation": {
    "valid": false,
    "complete": false,
    "status": "invalid",
    "error_count": 1,
    "warning_count": 0,
    "counts": {"TEACHER_UNAVAILABLE": 1},
    "summary": "1 conflict must be fixed before this timetable can be published (teacher not available: 1).",
    "conflicts": [
      {
        "code": "TEACHER_UNAVAILABLE",
        "severity": "error",
        "message": "Prof. Iyer is not available during Period 2 on Monday (CE-C (Engineering Maths)).",
        "day": "Mon",
        "period": 2,
        "entry_ids": ["MA201-CE-C-5"],
        "involved": {"teacher_id": "T02", "room_id": "R103", "batch_id": "CE-C", "subject_id": "MA201"},
        "suggested_entry_id": "MA201-CE-C-5"
      }
    ]
  },
  "needs_review": [
    {
      "entry_id": "MA201-CE-C-5",
      "label": "Engineering Maths for CE-C (Mon Period 2)",
      "codes": ["TEACHER_UNAVAILABLE"],
      "messages": ["Prof. Iyer is not available during Period 2 on Monday (CE-C (Engineering Maths))."]
    }
  ]
}
```

#### `POST /api/versions/{id}/publish` -> `PublishResponse`
Body (optional): `{"acknowledge_incomplete": boolean}` (default false).
* Hard conflicts -> **409 `PUBLISH_BLOCKED`** with `validation` (nothing changes).
* Unscheduled sessions and no acknowledgement -> **409 `ACKNOWLEDGE_INCOMPLETE`** (show the warning modal, then retry with `true`).
  The published version then has `is_complete: false` and `status_label: "Published (incomplete)"`.
* Only drafts can be published (`ALREADY_PUBLISHED`, `VERSION_NOT_EDITABLE` for archived).
* The previously published version becomes `archived` (kept, listed, restorable); `archived_version_id` tells which.
```json
{
  "version": {
    "id": 1,
    "dataset_id": 2,
    "seq": 1,
    "status": "published",
    "status_label": "Published",
    "label": "First run",
    "source": "generated",
    "created_at": "2026-10-16T17:52:26Z",
    "created_by": "coordinator",
    "published_at": "2026-10-16T17:52:26Z",
    "is_complete": true,
    "parent_version_id": null,
    "notes": "",
    "summary": {
      "total_sessions": 60, "scheduled": 60, "unscheduled": 0, "status": "valid_complete",
      "error_count": 0, "warning_count": 0, "needs_review_count": 0,
      "message": "Valid and complete: all 60 required sessions are scheduled with no conflicts."
    },
    "unscheduled": [],
    "validation": {
      "valid": true, "complete": true, "status": "valid_complete", "error_count": 0,
      "warning_count": 0, "counts": {},
      "summary": "Valid and complete: all 60 required sessions are scheduled with no conflicts.",
      "conflicts": []
    },
    "needs_review": [],
    "dataset": {
      "id": 2,
      "name": "Demo - CE Semester 3 (complete timetable)",
      "semester": "3",
      "days": ["Mon"],
      "periods": [{"period": 1, "start": "09:00", "end": "09:50", "is_break": false}]
    },
    "generation": {
      "status": "complete",
      "message": "Timetable generated: all 60 sessions are scheduled with no conflicts.",
      "findings": [],
      "stats": {
        "nodes": 60, "elapsed_ms": 13, "hit_limit": false, "exhausted": false, "max_nodes": 200000,
        "time_limit_s": 10.0, "total_sessions": 60, "scheduled_count": 60
      }
    }
  },
  "archived_version_id": null,
  "message": "First run is now the published timetable."
}
```
```json
{
  "detail": {
    "code": "ACKNOWLEDGE_INCOMPLETE",
    "message": "3 of 66 required session(s) are not scheduled. Publishing would mark this timetable as incomplete. Send acknowledge_incomplete=true to publish it anyway.",
    "unscheduled": 3, "total_sessions": 66
  }
}
```
```json
{
  "detail": {
    "code": "PUBLISH_BLOCKED",
    "message": "Version 2 cannot be published: 1 conflict must be fixed first. Prof. Iyer is not available during Period 2 on Monday (CE-C (Engineering Maths)).",
    "validation": {
      "valid": false,
      "complete": false,
      "status": "invalid",
      "error_count": 1,
      "warning_count": 0,
      "counts": {"TEACHER_UNAVAILABLE": 1},
      "summary": "1 conflict must be fixed before this timetable can be published (teacher not available: 1).",
      "conflicts": [
        {
          "code": "TEACHER_UNAVAILABLE",
          "severity": "error",
          "message": "Prof. Iyer is not available during Period 2 on Monday (CE-C (Engineering Maths)).",
          "day": "Mon",
          "period": 2,
          "entry_ids": ["MA201-CE-C-5"],
          "involved": {"teacher_id": "T02", "room_id": "R103", "batch_id": "CE-C", "subject_id": "MA201"},
          "suggested_entry_id": "MA201-CE-C-5"
        }
      ]
    }
  }
}
```

#### `POST /api/versions/{id}/restore` -> 201 `RestoreResponse`
Clones **any** version (draft, published, archived) into a **new draft** (`parent_version_id` = source, `source: "restored"`)
and revalidates it against the current data (see `version.summary`, `version.needs_review`). Body (optional):
`{"label"?, "notes"?, "created_by"?}`. The source is untouched.

#### `DELETE /api/versions/{id}` -> 204
Drafts and archived versions only; the published version -> 409 `CANNOT_DELETE_PUBLISHED`.

#### `GET /api/versions/{a}/compare/{b}` -> `CompareResult`
What changed going from version `a` to version `b` (same dataset, else 422 `DIFFERENT_DATASETS`). `moved` = day or
period changed, `room_changed`, `teacher_changed`; an entry that changed in several ways has `type: "changed"` and all
`aspects`. Classes only in `b` are `added`, only in `a` `removed`. `unchanged` is a count.
```json
{
  "from_version": {"id": 1, "label": "First run", "status": "published", "status_label": "Published"},
  "to_version": {"id": 2, "label": "Version 2", "status": "draft", "status_label": "Draft"},
  "summary": {
    "added": 0, "removed": 0, "moved": 1, "room_changed": 0, "teacher_changed": 0, "unchanged": 59,
    "changed_total": 1
  },
  "changes": [
    {
      "type": "moved",
      "aspects": ["moved"],
      "session_id": "CS201-CE-B-3",
      "subject_id": "CS201",
      "subject_name": "Data Structures",
      "batch_id": "CE-B",
      "batch_name": "CE-B",
      "text": "CS201 for CE-B moved Mon P6 → Mon P2",
      "before": {
        "entry_id": "CS201-CE-B-3", "session_id": "CS201-CE-B-3", "day": "Mon", "start_period": 6,
        "end_period": 6, "duration": 1, "start_time": "13:10", "end_time": "14:00",
        "subject_id": "CS201", "subject_name": "Data Structures", "subject_type": "lecture",
        "batch_id": "CE-B", "batch_name": "CE-B", "teacher_id": "T01", "teacher_name": "Dr. Sharma",
        "room_id": "R102", "room_name": "Room 102", "room_type": "classroom", "needs_review": false,
        "review_messages": []
      },
      "after": {
        "entry_id": "CS201-CE-B-3", "session_id": "CS201-CE-B-3", "day": "Mon", "start_period": 2,
        "end_period": 2, "duration": 1, "start_time": "09:50", "end_time": "10:40",
        "subject_id": "CS201", "subject_name": "Data Structures", "subject_type": "lecture",
        "batch_id": "CE-B", "batch_name": "CE-B", "teacher_id": "T01", "teacher_name": "Dr. Sharma",
        "room_id": "R102", "room_name": "Room 102", "room_type": "classroom", "needs_review": false,
        "review_messages": []
      }
    }
  ]
}
```

#### `GET /api/versions/{id}/analytics` -> `Analytics`
Teacher workload (periods per week, per day, utilisation of their available periods), room utilisation, batch load.
Lists shortened to 2 items:
```json
{
  "version_id": 1,
  "teachers": [
    {
      "teacher_id": "T01",
      "name": "Dr. Sharma",
      "sessions": 10,
      "periods_per_week": 10,
      "per_day": {"Mon": 2, "Tue": 2, "Wed": 2, "Thu": 2, "Fri": 2},
      "available_periods": 26,
      "utilization_pct": 38.5
    },
    {
      "teacher_id": "T02",
      "name": "Prof. Iyer",
      "sessions": 15,
      "periods_per_week": 15,
      "per_day": {"Mon": 3, "Tue": 3, "Wed": 3, "Thu": 3, "Fri": 3},
      "available_periods": 29,
      "utilization_pct": 51.7
    }
  ],
  "rooms": [
    {
      "room_id": "R101",
      "name": "Room 101",
      "room_type": "classroom",
      "periods_used": 18,
      "available_periods": 30,
      "utilization_pct": 60.0,
      "per_day": {"Mon": 3, "Tue": 3, "Wed": 4, "Thu": 4, "Fri": 4}
    },
    {
      "room_id": "R102",
      "name": "Room 102",
      "room_type": "classroom",
      "periods_used": 18,
      "available_periods": 30,
      "utilization_pct": 60.0,
      "per_day": {"Mon": 4, "Tue": 4, "Wed": 3, "Thu": 3, "Fri": 4}
    }
  ],
  "batches": [
    {
      "batch_id": "CE-A",
      "name": "CE-A",
      "sessions": 20,
      "periods_per_week": 22,
      "per_day": {"Mon": 5, "Tue": 5, "Wed": 4, "Thu": 4, "Fri": 4},
      "teaching_periods": 30,
      "utilization_pct": 73.3
    },
    {
      "batch_id": "CE-B",
      "name": "CE-B",
      "sessions": 20,
      "periods_per_week": 22,
      "per_day": {"Mon": 4, "Tue": 4, "Wed": 5, "Thu": 5, "Fri": 4},
      "teaching_periods": 30,
      "utilization_pct": 73.3
    }
  ],
  "total_periods_scheduled": 66,
  "teaching_periods_per_week": 30
}
```

### 4.5 Editing (drafts only)

Editing a **published or archived** version is rejected with **409 `VERSION_NOT_EDITABLE`** (message: *"... Restore it to a
new draft first"*). The same applies to the dry-run and unschedule endpoints. Every change is validated by the engine
first; an invalid change saves **nothing**.

Request body for moves (`MoveIn`): any of `{ "day"?: Day, "start_period"?: number, "room_id"?: string, "teacher_id"?: string }`;
omitted fields keep their value (at least one is required, else 422 `NOTHING_TO_CHANGE`). The class keeps its duration.

#### `POST /api/versions/{id}/entries/{entry_id}/validate-move` -> `MoveResult` (always 200)
Dry run, nothing saved. Call it while the user drags or picks a slot. `valid: false` -> show `message`, highlight
`affected_entries`, offer `suggestions`.
```json
{
  "valid": false,
  "message": "Dr. Sharma is already assigned to CE-A during Period 5 on Monday (Data Structures). 2 more issues also block this change.",
  "entry": {
    "entry_id": "CS201-CE-B-3", "session_id": "CS201-CE-B-3", "day": "Mon", "start_period": 5,
    "end_period": 5, "duration": 1, "start_time": "12:20", "end_time": "13:10",
    "subject_id": "CS201", "subject_name": "Data Structures", "subject_type": "lecture",
    "batch_id": "CE-B", "batch_name": "CE-B", "teacher_id": "T01", "teacher_name": "Dr. Sharma",
    "room_id": "R102", "room_name": "Room 102", "room_type": "classroom", "needs_review": false,
    "review_messages": []
  },
  "conflicts": [
    {
      "code": "TEACHER_OVERLAP",
      "severity": "error",
      "message": "Dr. Sharma is already assigned to CE-A during Period 5 on Monday (Data Structures).",
      "day": "Mon",
      "period": 5,
      "entry_ids": ["CS201-CE-A-5", "CS201-CE-B-3"],
      "involved": {"teacher_id": "T01", "room_id": null, "batch_id": null, "subject_id": null},
      "suggested_entry_id": "CS201-CE-B-3"
    },
    {
      "code": "ROOM_OVERLAP",
      "severity": "error",
      "message": "Room 102 is already booked for CE-B (Engineering Maths) during Period 5 on Monday.",
      "day": "Mon",
      "period": 5,
      "entry_ids": ["CS201-CE-B-3", "MA201-CE-B-3"],
      "involved": {"teacher_id": null, "room_id": "R102", "batch_id": null, "subject_id": null},
      "suggested_entry_id": "CS201-CE-B-3"
    }
  ],
  "affected_entries": [
    {
      "entry_id": "CS201-CE-A-5", "session_id": "CS201-CE-A-5", "day": "Mon", "start_period": 5,
      "end_period": 5, "duration": 1, "start_time": "12:20", "end_time": "13:10",
      "subject_id": "CS201", "subject_name": "Data Structures", "subject_type": "lecture",
      "batch_id": "CE-A", "batch_name": "CE-A", "teacher_id": "T01", "teacher_name": "Dr. Sharma",
      "room_id": "R101", "room_name": "Room 101", "room_type": "classroom", "needs_review": false,
      "review_messages": []
    },
    {
      "entry_id": "MA201-CE-B-3", "session_id": "MA201-CE-B-3", "day": "Mon", "start_period": 5,
      "end_period": 5, "duration": 1, "start_time": "12:20", "end_time": "13:10",
      "subject_id": "MA201", "subject_name": "Engineering Maths", "subject_type": "lecture",
      "batch_id": "CE-B", "batch_name": "CE-B", "teacher_id": "T02", "teacher_name": "Prof. Iyer",
      "room_id": "R102", "room_name": "Room 102", "room_type": "classroom", "needs_review": false,
      "review_messages": []
    }
  ],
  "suggestions": [
    {
      "day": "Mon", "start_period": 6, "end_period": 6, "duration": 1, "start_time": "13:10",
      "end_time": "14:00", "room_id": "R102", "room_name": "Room 102", "teacher_id": "T01",
      "teacher_name": "Dr. Sharma", "label": "Monday Period 6 in Room 102"
    },
    {
      "day": "Mon", "start_period": 7, "end_period": 7, "duration": 1, "start_time": "14:00",
      "end_time": "14:50", "room_id": "R102", "room_name": "Room 102", "teacher_id": "T01",
      "teacher_name": "Dr. Sharma", "label": "Monday Period 7 in Room 102"
    }
  ]
}
```
(`conflicts` shortened to 2 items.) A valid dry run:
```json
{
  "valid": true,
  "message": "No conflicts: this change is safe to save.",
  "entry": {
    "entry_id": "CS201-CE-B-3", "session_id": "CS201-CE-B-3", "day": "Mon", "start_period": 6,
    "end_period": 6, "duration": 1, "start_time": "13:10", "end_time": "14:00",
    "subject_id": "CS201", "subject_name": "Data Structures", "subject_type": "lecture",
    "batch_id": "CE-B", "batch_name": "CE-B", "teacher_id": "T01", "teacher_name": "Dr. Sharma",
    "room_id": "R102", "room_name": "Room 102", "room_type": "classroom", "needs_review": false,
    "review_messages": []
  },
  "conflicts": [],
  "affected_entries": [],
  "suggestions": []
}
```

#### `PATCH /api/versions/{id}/entries/{entry_id}` -> `EditResponse`
Applies the change **only if it is valid**; otherwise **409 `MOVE_REJECTED`** and nothing is saved. The 409 `detail` is
the error envelope *plus every MoveResult field* (`valid`, `entry`, `conflicts`, `affected_entries`, `suggestions`):
```json
{
  "detail": {
    "code": "MOVE_REJECTED",
    "message": "The change was not saved. Dr. Sharma is already assigned to CE-A during Period 5 on Monday (Data Structures). 2 more issues also block this change.",
    "valid": false,
    "entry": {
      "entry_id": "CS201-CE-B-3", "session_id": "CS201-CE-B-3", "day": "Mon", "start_period": 5,
      "end_period": 5, "duration": 1, "start_time": "12:20", "end_time": "13:10",
      "subject_id": "CS201", "subject_name": "Data Structures", "subject_type": "lecture",
      "batch_id": "CE-B", "batch_name": "CE-B", "teacher_id": "T01", "teacher_name": "Dr. Sharma",
      "room_id": "R102", "room_name": "Room 102", "room_type": "classroom", "needs_review": false,
      "review_messages": []
    },
    "conflicts": [
      {
        "code": "TEACHER_OVERLAP",
        "severity": "error",
        "message": "Dr. Sharma is already assigned to CE-A during Period 5 on Monday (Data Structures).",
        "day": "Mon",
        "period": 5,
        "entry_ids": ["CS201-CE-A-5"],
        "involved": {"teacher_id": "T01", "room_id": null, "batch_id": null, "subject_id": null},
        "suggestions": [],
        "suggested_entry_id": "CS201-CE-B-3"
      }
    ],
    "affected_entries": [
      {
        "entry_id": "CS201-CE-A-5", "session_id": "CS201-CE-A-5", "day": "Mon", "start_period": 5,
        "end_period": 5, "duration": 1, "start_time": "12:20", "end_time": "13:10",
        "subject_id": "CS201", "subject_name": "Data Structures", "subject_type": "lecture",
        "batch_id": "CE-A", "batch_name": "CE-A", "teacher_id": "T01", "teacher_name": "Dr. Sharma",
        "room_id": "R101", "room_name": "Room 101", "room_type": "classroom", "needs_review": false,
        "review_messages": []
      }
    ],
    "suggestions": [
      {
        "day": "Mon", "start_period": 6, "end_period": 6, "duration": 1, "start_time": "13:10",
        "end_time": "14:00", "room_id": "R102", "room_name": "Room 102", "teacher_id": "T01",
        "teacher_name": "Dr. Sharma", "label": "Monday Period 6 in Room 102"
      }
    ]
  }
}
```
Success returns the refreshed version (`entries` shortened here):
```json
{
  "message": "Change saved. No conflicts.",
  "entry": {
    "entry_id": "CS201-CE-B-3", "session_id": "CS201-CE-B-3", "day": "Mon", "start_period": 6,
    "end_period": 6, "duration": 1, "start_time": "13:10", "end_time": "14:00",
    "subject_id": "CS201", "subject_name": "Data Structures", "subject_type": "lecture",
    "batch_id": "CE-B", "batch_name": "CE-B", "teacher_id": "T01", "teacher_name": "Dr. Sharma",
    "room_id": "R102", "room_name": "Room 102", "room_type": "classroom", "needs_review": false,
    "review_messages": []
  },
  "version": {
    "id": 1,
    "dataset_id": 2,
    "seq": 1,
    "status": "draft",
    "status_label": "Draft",
    "label": "First run",
    "source": "generated",
    "created_at": "2026-10-16T17:52:26Z",
    "created_by": "coordinator",
    "published_at": null,
    "is_complete": true,
    "parent_version_id": null,
    "notes": "",
    "entries": [
      {
        "entry_id": "CS291-CE-A-1", "session_id": "CS291-CE-A-1", "day": "Mon", "start_period": 1,
        "end_period": 2, "duration": 2, "start_time": "09:00", "end_time": "10:40",
        "subject_id": "CS291", "subject_name": "DS Lab", "subject_type": "practical",
        "batch_id": "CE-A", "batch_name": "CE-A", "teacher_id": "T05", "teacher_name": "Mr. Das",
        "room_id": "LAB1", "room_name": "Computer Lab 1", "room_type": "lab", "needs_review": false,
        "review_messages": []
      }
    ],
    "unscheduled": [],
    "needs_review": []
  }
}
```

#### `POST /api/versions/{id}/entries/{entry_id}/unschedule` -> `EditResponse`
Takes a class off the grid; it appears in `version.unscheduled` with reason code `MANUALLY_UNSCHEDULED` and the version becomes
incomplete. `entry` is `null` in the response.
```json
{
  "message": "Operating Systems for CE-C (Mon Period 1) was moved to the unscheduled list.",
  "entry": null,
  "version": {
    "id": 3,
    "dataset_id": 2,
    "seq": 3,
    "status": "draft",
    "status_label": "Draft",
    "label": "Fix for T02",
    "source": "restored",
    "created_at": "2026-10-16T17:52:27Z",
    "created_by": "coordinator",
    "published_at": null,
    "is_complete": false,
    "parent_version_id": 1,
    "notes": "",
    "summary": {
      "total_sessions": 60, "scheduled": 59, "unscheduled": 1, "status": "invalid", "error_count": 1,
      "warning_count": 1, "needs_review_count": 1,
      "message": "1 conflict must be fixed before this timetable can be published (teacher not available: 1)."
    },
    "unscheduled": [
      {
        "session_id": "CS203-CE-C-4",
        "subject_id": "CS203",
        "subject_name": "Operating Systems",
        "subject_type": "lecture",
        "batch_id": "CE-C",
        "batch_name": "CE-C",
        "teacher_id": "T04",
        "teacher_name": "Ms. Kapoor",
        "duration": 1,
        "index": 4,
        "of": 4,
        "reasons": ["Removed from the timetable by the coordinator."],
        "reason_codes": ["MANUALLY_UNSCHEDULED"],
        "hints": ["Choose one of the suggested slots to place it again."]
      }
    ],
    "needs_review": [
      {
        "entry_id": "MA201-CE-C-5",
        "label": "Engineering Maths for CE-C (Mon Period 2)",
        "codes": ["TEACHER_UNAVAILABLE"],
        "messages": ["Prof. Iyer is not available during Period 2 on Monday (CE-C (Engineering Maths))."]
      }
    ]
  }
}
```

#### `GET /api/versions/{id}/entries/{entry_id}/suggestions?limit=5` -> `Suggestion[]`
Alternative valid slots for a scheduled class (nearest to its current slot first; its own slot is not returned).
```json
[
  {
    "day": "Mon", "start_period": 6, "end_period": 6, "duration": 1, "start_time": "13:10",
    "end_time": "14:00", "room_id": "R102", "room_name": "Room 102", "teacher_id": "T01",
    "teacher_name": "Dr. Sharma", "label": "Monday Period 6 in Room 102"
  },
  {
    "day": "Mon", "start_period": 7, "end_period": 7, "duration": 1, "start_time": "14:00",
    "end_time": "14:50", "room_id": "R102", "room_name": "Room 102", "teacher_id": "T01",
    "teacher_name": "Dr. Sharma", "label": "Monday Period 7 in Room 102"
  }
]
```

#### Unscheduled sessions
* `GET /api/versions/{id}/unscheduled/{session_id}/suggestions?limit=5` -> `Suggestion[]` (best spread first; `[]` when no valid slot exists - then the item's `reasons`/`hints` explain why). 409 `ALREADY_SCHEDULED` if the session is on the grid.
```json
[
  {
    "day": "Mon", "start_period": 1, "end_period": 1, "duration": 1, "start_time": "09:00",
    "end_time": "09:50", "room_id": "R103", "room_name": "Room 103", "teacher_id": "T04",
    "teacher_name": "Ms. Kapoor", "label": "Monday Period 1 in Room 103"
  },
  {
    "day": "Mon", "start_period": 1, "end_period": 1, "duration": 1, "start_time": "09:00",
    "end_time": "09:50", "room_id": "R101", "room_name": "Room 101", "teacher_id": "T04",
    "teacher_name": "Ms. Kapoor", "label": "Monday Period 1 in Room 101"
  }
]
```
* `POST /api/versions/{id}/unscheduled/{session_id}/validate-place` body `{ "day": Day, "start_period": number, "room_id": string, "teacher_id"?: string }` -> `MoveResult` (200).
```json
{
  "valid": true,
  "message": "No conflicts: this change is safe to save.",
  "entry": {
    "entry_id": "CS203-CE-C-4", "session_id": "CS203-CE-C-4", "day": "Mon", "start_period": 1,
    "end_period": 1, "duration": 1, "start_time": "09:00", "end_time": "09:50",
    "subject_id": "CS203", "subject_name": "Operating Systems", "subject_type": "lecture",
    "batch_id": "CE-C", "batch_name": "CE-C", "teacher_id": "T04", "teacher_name": "Ms. Kapoor",
    "room_id": "R103", "room_name": "Room 103", "room_type": "classroom", "needs_review": false,
    "review_messages": []
  },
  "conflicts": [],
  "affected_entries": [],
  "suggestions": []
}
```
* `POST /api/versions/{id}/unscheduled/{session_id}/place` same body -> `EditResponse`; invalid -> 409 `MOVE_REJECTED`, nothing saved.
```json
{
  "detail": {
    "code": "MOVE_REJECTED",
    "message": "The placement was not saved. CE-C (Operating Systems) cannot be held in Period 4 on Monday because it is a break.",
    "valid": false,
    "conflicts": [
      {
        "code": "BLOCKED_PERIOD",
        "severity": "error",
        "message": "CE-C (Operating Systems) cannot be held in Period 4 on Monday because it is a break.",
        "day": "Mon",
        "period": 4,
        "entry_ids": ["CS203-CE-C-4"],
        "involved": {"teacher_id": "T04", "room_id": "R101", "batch_id": "CE-C", "subject_id": "CS203"},
        "suggestions": [],
        "suggested_entry_id": "CS203-CE-C-4"
      }
    ]
  }
}
```

### 4.6 Export

#### `GET /api/versions/{id}/export.csv`
One row per **scheduled** class, UTF-8 with BOM (Excel friendly), `Content-Disposition: attachment; filename="smartslot-<dataset>-<version>.csv"`.
Columns, in order: `session_id, batch_id, batch_name, subject_id, subject_name, session_type, teacher_id, teacher_name,
room_id, room_name, room_type, day, start_period, end_period, duration, start_time, end_time`. Cells starting with
`= + - @` are prefixed with `'` so spreadsheets cannot run them as formulas.
```csv
session_id,batch_id,batch_name,subject_id,subject_name,session_type,teacher_id,teacher_name,room_id,room_name,room_type,day,start_period,end_period,duration,start_time,end_time
CS291-CE-A-1,CE-A,CE-A,CS291,DS Lab,practical,T05,Mr. Das,LAB1,Computer Lab 1,lab,Mon,1,2,2,09:00,10:40
CS202-CE-B-1,CE-B,CE-B,CS202,DBMS,lecture,T03,Dr. Mehta,R102,Room 102,classroom,Mon,1,1,1,09:00,09:50
CS203-CE-C-4,CE-C,CE-C,CS203,Operating Systems,lecture,T04,Ms. Kapoor,R103,Room 103,classroom,Mon,1,1,1,09:00,09:50
```

#### `GET /api/versions/{id}/export.pdf?view=batch|teacher|room&id=<entity id>`
Landscape A4. `view` defaults to `batch`. With `id` -> one page for that batch / teacher / room (unknown id -> 404 `ENTITY_NOT_FOUND`);
without `id` -> **one page per entity** of that view (demo: 3 batch pages, 6 teacher pages, 4 room pages).
Each page has the title, semester, version label, a **PUBLISHED / DRAFT / ARCHIVED** badge (plus **INCOMPLETE** when sessions are
unscheduled), the generation date, the weekly grid with a shaded **Break** row, readable subject / teacher / room per cell,
multi-period practicals merged into one tall cell, and a colour legend. Download from the UI with a plain
`<a href="/api/versions/1/export.pdf?view=teacher&id=T01" download>` or `fetch` + blob.

---

## 5. Behaviour notes the UI should know

* **Published is immutable.** The only way to change published content is `restore` -> edit the draft -> `publish`. Publishing archives the old one.
* **Regenerate never overwrites** the published version; it just adds another draft.
* **Rejected edits are free.** `PATCH`/`place` that return 409 or 422 changed nothing; the grid you already have is still correct.
* **Import status is a property of the import.** `import_status` does not change when you later edit config/availability. To fix a
  `has_errors` dataset, import corrected files (and delete the old dataset).
* **Validation is live.** Version summaries are recomputed from stored entries each time, so they always reflect the current data.
* **Determinism.** The same dataset generates the same timetable and validation messages every time.
* **Concurrency.** Writes are transactional; two edits cannot both pass validation against stale data.

---

## 6. Code lists

**Import issue codes**

| Level | Code | Meaning |
|-------|------|---------|
| file | `MISSING_FILE` `EMPTY_FILE` `WRONG_HEADER` `MISSING_COLUMN` `DUPLICATE_COLUMN` `NOT_CSV` `BAD_ENCODING` `WRONG_DELIMITER` `MALFORMED_CSV` `FILE_TOO_LARGE` `TOO_MANY_ROWS` `BAD_ZIP` `ZIP_TOO_LARGE` `ZIP_TOO_MANY_FILES` `ZIP_ENCRYPTED` `DUPLICATE_FILE` | errors that make a whole file unusable |
| row | `MISSING_FIELD` `NOT_A_NUMBER` `OUT_OF_RANGE` `INVALID_CHOICE` (room_type, session_type, available, is_break) `INVALID_ID` `TOO_LONG` `TOO_MANY_CELLS` | cell problems |
| row | `DUPLICATE_ID` `DUPLICATE_DAY` `DUPLICATE_PERIOD` `DUPLICATE_REQUIREMENT` `ID_CLASH` (teacher and room share an id) | duplicates |
| row | `UNKNOWN_TEACHER` `UNKNOWN_SUBJECT` `UNKNOWN_BATCH` `UNKNOWN_RESOURCE` `UNKNOWN_PERIOD` `DAY_NOT_IN_DAYS_FILE` `INVALID_DAY` | references |
| row | `INVALID_TIME` `END_NOT_AFTER_START` | periods.csv |
| dataset | `NO_TEACHING_PERIODS` | every period is a break (error) |
| warning | `UNKNOWN_FILE` `UNKNOWN_COLUMN` `UNSAFE_ZIP_PATH` `AVAILABILITY_ON_BREAK` `REDUNDANT_AVAILABILITY` `DUPLICATE_AVAILABILITY` `BATCH_WITHOUT_REQUIREMENTS` `TEACHER_WITHOUT_REQUIREMENTS` `SUBJECT_WITHOUT_REQUIREMENTS` `SEMESTER_MISMATCH` `PERIOD_GAP` `PERIOD_OVERLAP` `DURATION_TOO_LONG` | importable, but worth a look |

A teacher whose requirements exceed their weekly capacity is **not** an import problem: the scheduler reports it as unscheduled sessions with reasons.

**Unscheduled `reason_codes`**: `INVALID_REFERENCE INVALID_DURATION NO_TEACHING_BLOCK TEACHER_NEVER_FREE NO_SUITABLE_ROOM ROOM_TOO_SMALL ROOM_NEVER_FREE`
(no candidate slot), `TEACHER_OVERLOAD BATCH_OVERLOAD ROOM_OVERLOAD` (provable by counting), `NO_FREE_SLOT SEARCH_LIMIT` (search),
plus `MANUALLY_UNSCHEDULED` and `NOT_SCHEDULED` added by the API layer.

**Conflict `code`s**: `TEACHER_OVERLAP ROOM_OVERLAP BATCH_OVERLAP TEACHER_UNAVAILABLE ROOM_UNAVAILABLE ROOM_CAPACITY ROOM_TYPE INVALID_DURATION OUTSIDE_WORKING_HOURS BLOCKED_PERIOD INVALID_REFERENCE MISSING_SESSION`.
