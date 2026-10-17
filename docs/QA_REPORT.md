# SmartSlot - QA report (Phase 5)

Independent QA pass: real Edge browser (playwright-core, headless) against the running app (FastAPI :8000, Vite :5173), plus direct API
probing, an independent clash checker written from the CSVs (it does **not** import the engine) and a read of the code paths most likely
to hide bugs. Viewports: 768x1024 (tablet), 1366x768 (laptop), 1920x1080.

Test scripts were kept outside the repo. Final automated results: 166 API probe checks (164 pass; the other 2 were wrong expectations in
my probe - a zip that deliberately contains `sub/teachers.csv` next to `teachers.csv` is correctly reported as a duplicate file, and two
requirement rows for one subject+batch with different teachers are valid co-teaching, not an error), about 180 browser checks (all
pass after the fixes below), backend `pytest` 206 passed, `npm run typecheck` and `npm run build` clean.

## 1. Acceptance criteria (PRD section 15)

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Import the sample ERP dataset | PASS | UI "Load demo dataset" and a real multi-file upload of `sample_data/feasible` both give the validation summary (6 teachers, 5 subjects, 3 batches, 4 rooms, 15 requirements, 60 sessions/week, 13 unavailable slots) and select the dataset in the header. Zip upload and BOM/CRLF files also import. |
| 2 | Invalid records identified with actionable messages | PASS | `sample_data/invalid` (UI file upload): 35 errors + 1 warning, every row has file / row / field / value / what is wrong / how to fix; per-file filter chips; generation blocked (422 `IMPORT_HAS_ERRORS`, Generate page shows blocked state). Empty, non-UTF-8, semicolon, binary, oversized (>2 MB), 25 000-row, wrong-extension and header-only files all give readable per-file errors, never a 500. |
| 3 | Complete timetable for the feasible dataset | PASS | Generate -> "Complete & valid - all 60 sessions scheduled, 0 conflicts" (13 ms, 60 nodes). Deterministic: regenerating gives an identical timetable. |
| 4 | No teacher / room / batch overlaps | PASS | Independent checker (teacher, room, batch overlap per period) on the API entries **and on the exported CSV**: 0 violations. Negative test (deliberately corrupted entries) proves the checker detects overlaps. |
| 5 | Capacity, room type, availability respected | PASS | Same checker: capacity, lab/classroom type, teacher+room availability, break periods, 2-period practicals contiguous - 0 violations. Edits: lecture->lab, practical->classroom, CE-A(60)->Room 103(48), teacher on unavailable slot all rejected with plain English. |
| 6 | Deliberately impossible requirement reported | PASS | Infeasible sample -> "Partial - 63 of 66 scheduled, 3 could not be placed"; reasons + hints per session ("Mr. Das needs 12 sessions of 2 or more consecutive periods per week, but only 9 such blocks fit..."); never labelled complete; publishing needs an explicit acknowledgement. Search-limit run (`max_nodes=1`) says "No complete solution found within the search limit", not "impossible". Batch of 500 students (no room fits) -> unscheduled with ROOM_TOO_SMALL. |
| 7 | Invalid manual edit rejected with explanation | PASS | Drag + Edit dialog: teacher clash, batch clash, room clash, break row, unavailable slot, lab block, last-period/lunch-crossing practical, wrong room type, too-small room, busy teacher, unknown ids. API answers 409 `MOVE_REJECTED`, nothing saved (entries byte-identical before/after), UI shows "Move blocked" / red live-validation box, Save disabled, Esc closes. |
| 8 | Valid manual edit saved and revalidated | PASS | Drag to a green slot and Edit-dialog suggestion chips both save; toast + "Last change" card + header badge stay "Valid - Complete"; Undo restores the original timetable exactly; unschedule -> "Valid - 1 unscheduled" -> place again -> complete. |
| 9 | View by teacher, room and batch | PASS | All three views, entity picker, prev/next, deep links (`/timetable?view=room&id=LAB1`), unavailable slots hatched in teacher/room views, lab blocks span 2 periods. |
| 10 | Export and publish a verified timetable | PASS | Publish dialog runs a fresh validation; CSV (60 rows) matches the API entry-for-entry (0 mismatches); PDF (3 batch / 6 teacher / 4 room pages) rendered with PyMuPDF and inspected: no clipping or overlap, merged lab blocks, Break row, PUBLISHED / INCOMPLETE badges, legend. Formula cells are neutralised in CSV. |
| 11 | Previous published version remains recoverable | PASS | Regenerate leaves the published version **byte-for-byte identical** (API JSON compared); publishing a new draft archives the old one; restoring an archived version creates a draft with identical entries and leaves the archive untouched; only one version is ever published (unique index). |
| 12 | Demo runs locally without a live ERP | PASS | Everything above ran from bundled `sample_data/` on localhost; no network calls other than localhost. |

## 2. Edge cases (PRD section 10) and the extra break-it list

| Edge case | Result | Evidence |
|-----------|--------|----------|
| Teacher unavailable | PASS | Generator avoids it; manual placement rejected ("Dr. Sharma is not available during Period 3 on Monday"). |
| Room too small | PASS | "Room 103 seats 48 but CE-A has 60 students." Option list labels it "too small for 60". |
| Practical needs a lab | PASS | Practical -> classroom rejected; lecture -> lab rejected. |
| No feasible slot | PASS | Unscheduled list with reasons/hints, suggestions empty when none exist. |
| Duplicate ERP records | PASS | `DUPLICATE_ID` with the row of the first occurrence; teacher-id == room-id flagged (`ID_CLASH`); same file twice flagged. |
| Invalid teacher / room id | PASS | `UNKNOWN_TEACHER` etc. with row and field; edit with unknown teacher/room/entry/version -> readable 404/409. |
| Two sessions need the same teacher+period | PASS | Different periods or reported unscheduled (infeasible sample). |
| Manual swap creates a clash | PASS | See criterion 7. Two simultaneous conflicting PATCHes: exactly one 200, one 409; draft stays at 0 errors. |
| Teacher unavailable after generation | PASS | Configure shows "1 scheduled class now needs review"; published version untouched (entries identical), header turns red "1 conflict"; "Create fixed draft" -> flagged class (amber) -> move it -> publish; broken draft cannot be published. Room capacity change after publish flags ROOM_CAPACITY the same way. |
| Regenerate must not overwrite published | PASS | Byte-identical comparison. |
| Partial scheduling | PASS | Three separate states in UI/API: complete, "Valid - N unscheduled" (amber), "N conflicts" (red); "Published (incomplete)" label everywhere. |
| Empty / incomplete dataset | PASS | Header-only templates, empty file, missing files -> errors; generate blocked with a readable message. |
| Multiple departments / shared resources | PASS (by design) | Teachers/rooms are checked globally in one dataset; department is metadata only (documented limitation: one dataset = one semester). |
| Upload attacks | PASS | Zip with `../`, `/abs`, `C:\` and nested paths: unsafe members skipped with warnings, nothing written to disk; fake zip, zip bomb (30 MB expanded), 60-member zip, 17 MB body (413), filename `../../teachers.csv` all handled. |
| Edit/validate/unschedule/place/delete on published or archived | PASS | All 409 `VERSION_NOT_EDITABLE` / `CANNOT_DELETE_PUBLISHED` with plain messages; UI shows the read-only banner and no class is draggable. |
| Publish gates | PASS | Hard conflicts -> 409 `PUBLISH_BLOCKED` (UI lists them, button disabled); unscheduled -> `ACKNOWLEDGE_INCOMPLETE` (checkbox required); `acknowledge_incomplete:"yes please"` does not bypass; re-publish / publish archived -> 409. |
| Delete dataset | PASS | Without `force` -> 409 `DATASET_HAS_PUBLISHED_VERSION`; with `force=true` dataset and all versions removed. |
| Browser reload on every route | PASS | Deep links for all 7 routes + query variants; unknown route redirects home; bad `id`/`view` params fall back to defaults. |
| Stale localStorage ids | PASS | dataset 9999/version 9999, version of another dataset, dataset deleted elsewhere: app recovers on all five data pages, no 404 storm, never blank. |
| API down mid-session | PASS (after fix 2) | Edit dialog, drop, generate, CSV export, full reload all show "Cannot reach the SmartSlot server. Make sure it is running (start.ps1) and try again."; Retry recovers. |
| Stale drag (slot taken after the green hint was shown) | PASS | Drop is re-validated by the server: "Move blocked" dialog, entries unchanged. |
| Delete dataset in the UI | PASS | Published dataset shows the "published timetable will be deleted too" warning inside the confirm dialog; Esc keeps it; deleting the last dataset returns to the empty state. |
| Configure page edits | PASS | Room capacity 0 refused, 20 saved -> existing draft immediately flagged ROOM_CAPACITY, restoring clears it; adding/removing a period works and old versions still render; invalid search limits refused with plain text. |
| Keyboard | PASS | Esc closes the edit drawer, details drawer, blocked dialog, delete dialog; focused classes show a 2 px outline. |
| Responsive | PASS | 9 routes x 3 viewports: no horizontal page scroll, no element sticking out of the viewport, tablet shows icon-only sidebar and wrapped controls cleanly. |

## 3. Bugs found and fixed

| # | Severity | Bug | Root cause | Fix |
|---|----------|-----|-----------|-----|
| 1 | Medium (demo risk) | Dropping a class on the **lunch-break band** did nothing at all - no message. The PRD asks for a rejection with an explanation. | The break band in `TimetableGrid` had no drop handlers, so the browser silently cancelled the drag. | `TimetableGrid.tsx`: the break band now accepts drops, maps the pointer x to a day and routes through the normal dry-run -> "Move blocked: ... cannot be held in Period 4 on Wednesday because it is a break" dialog with alternatives. |
| 2 | Medium | With the backend stopped, the UI said "The server answered with an error (500)" (edit dialog, generate, exports, full-page error: "Cannot reach the SmartSlot server - The server answered with an error (500)"). | The Vite dev proxy answers an empty-body 500 when the API process is down; `parseError` treated it as an application error. | `api/client.ts` and `lib/download.ts`: a 5xx without the API's JSON envelope is reported as `NETWORK_ERROR` with the standard "Cannot reach the SmartSlot server..." text; `AppShell` no longer repeats the sentence. |
| 3 | High (data/state) | **Stale-request race:** start Generate (or any edit/publish) for dataset A, switch to dataset B before it returns. When the response arrived the app adopted A's version while B was selected: header showed A's "Valid - Complete" version for B, A's version entered B's version list and the Timetable page was stuck on the loading skeleton forever. | `AppState.adoptVersion` accepted any version regardless of the selected dataset. | `state/AppState.tsx`: `adoptVersion` ignores a version whose `dataset_id` is not the selected dataset (the work itself is saved on the server and appears when A is reopened). Reproduced with a delayed route before the fix, verified after. |

No backend defects were found, so no new backend regression tests were needed; the existing 206 tests stay green. (Fixes 1-3 are UI-only; the repo has no frontend test runner, so they are covered by the Playwright scenarios described above.)

## 4. Residual known issues (not fixed, low risk)

* `PUT /datasets/{id}/config` (API only; the UI cannot produce these) accepts overlapping period times, non-contiguous period numbers (e.g. only "period 3") and times that wrap past midnight without a warning. The importer does warn for the same data in CSV form.
* A no-op edit (same day/period/room/teacher) is accepted and answered "Change saved. No conflicts." instead of `NOTHING_TO_CHANGE`; harmless.
* When a move is blocked for several reasons the dialog's first sentence is the first conflict in day/period order (e.g. "CE-A already has Engineering Maths" for a lab dropped on Period 3), while the "crosses the lunch break" reason is listed second. All reasons are shown.
* While dragging, the red/green drop marker covers the small "LAB" badge of a block (cosmetic, only during a drag).
* Two datasets can have the same name; generating twice quickly (parallel requests) creates two drafts - by design.
* Dev-only: `POST /api/dev/reset` wipes the database when `SMARTSLOT_DEV=1`; start.ps1 sets it. Do not set it on a real installation.

## 5. Most fragile area for the demo

HTML5 drag-and-drop needs the whole grid on screen (a tall browser window or zoom-out) and a steady pointer; use the Edit session dialog as the fallback for the "clash" step. Generation, publish and export are deterministic and fast.
