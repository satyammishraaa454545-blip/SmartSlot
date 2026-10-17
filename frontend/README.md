# SmartSlot web UI

React 18 + TypeScript + Vite + Tailwind CSS (v3) + react-router. No auth, no state library: one React context plus a small typed `fetch` client.

```powershell
cd frontend
npm install
npm run dev          # http://localhost:5173  (proxies /api -> http://127.0.0.1:8000)
npm run typecheck    # tsc -b --noEmit
npm run build        # tsc -b && vite build  -> dist/
```

The API must be running (`..\start.ps1 -Backend`, or `start.ps1` for both). The proxy target is `127.0.0.1`, not `localhost`, on purpose (Node resolves `localhost` to `::1`, uvicorn listens on IPv4 only). Open the UI as `http://localhost:5173`.

## Folder structure (`src/`)

| Path | What it holds |
|------|---------------|
| `main.tsx`, `App.tsx` | Providers and the **route table** (add new pages here). |
| `api/` | `client.ts` (typed `request()`, `ApiError`, `errorMessage`), `types.ts` (every object of `docs/API.md`), `datasets.ts`, `versions.ts` (already wraps editing, publish, restore, compare, analytics, exports for the next phase). |
| `state/AppState.tsx` | `useApp()`: dataset list, selected dataset (full detail), versions list, selected version (full detail), `lastGeneration`; selection is saved in localStorage and stale ids are tolerated. Actions: `selectDataset/Version`, `refresh*`, `adoptVersion(v)` (call after generate / edit / publish / restore), `applyDatasetDetail`, `patchDatasetLocal` (optimistic edits). |
| `components/layout/` | `AppShell` (header + sidebar + `<Outlet/>`), `Header`, `Sidebar` (`NAV_ITEMS`), `PageHeader`, `RequireDataset`. |
| `components/status/StatusBadges.tsx` | `VersionStatusChip`, `ValidationBadge` (green / amber / red recipe from the API doc). |
| `components/ui/` | `Button, Card, Badge, Banner, Modal/ConfirmDialog/Drawer, Toast (useToast), Segmented, Spinner/Skeleton, EmptyState`. |
| `features/import/` | Upload (multi-file / zip / drag and drop), demo loaders, validation summary (counts, errors table, file filter), dataset list + delete (handles `force=true`), template docs. |
| `features/configure/` | Days and periods editor, availability grid (optimistic toggles with rollback), rooms / batches inline edit, requirements table. |
| `features/generate/` | Generate button, readiness checks, advanced search limit, result banner (`ResultPanel`). |
| `features/timetable/` | `TimetablePage` (read-only banner, needs-review banner, last-change card, panels), **`TimetableGrid`**, `EntryBlock`, `EntryDrawer`, `Panels` (unscheduled + conflicts), `gridModel.ts`, `colors.ts`, `entities.ts`. |
| `features/timetable/edit/` | Manual editing (drafts only): `useTimetableEditor` (state + writes + undo), `EditSessionDialog` (edit **and** place, live pre-validation), `MoveBlockedDialog` (drag and drop rejection), `useDragCheck` (dry-runs every slot while dragging), `LastChangeCard`, `VersionBanners`, `MoveFeedback` (conflict list, clashing classes, suggestion chips), `helpers.ts`. |
| `features/versions/` | `VersionsPage` (published banner, version timeline, validate / publish / restore / delete / compare), `PublishDialog` (fresh validation report, incomplete acknowledgement), `ComparePanel` (diff), `ExportCard` (CSV, PDF, print), `useVersionActions` (restore / publish / delete that keep header + lists in sync). |
| `features/print/` | `PrintSheet`: one timetable per page, rendered into `<body>`; `index.css` hides the app while it exists. |
| `features/insights/` | `InsightsPage` (teacher workload, room utilisation, batch load as plain CSS bars + a table view) and `insights.ts` (plain-English observations). |
| `lib/` | `format.ts` (dates, plurals, times), `storage.ts` (safe localStorage), `download.ts` (fetch + save-as for CSV / PDF). |

## Timetable grid API

`<TimetableGrid>` is controlled and presentational (it never fetches or mutates):

```ts
days: Day[]; periods: PeriodDef[];           // from version.dataset
entries: Entry[]; view: "batch"|"teacher"|"room"; entityId: string;   // grid filters entries itself
colorOf: (subjectId) => SubjectColor;
unavailable?: {day, period, label}[];        // hatched slots + tooltip ("Mr. Das unavailable")
conflictEntryIds?: ReadonlySet<string>;      // red outline
selectedEntryId?: string | null; highlightSlots?: {day, period}[];
onEntryClick?(entry); onCellClick?({day, period});   // onCellClick only for EMPTY slots (they then render as buttons)
onDropEntry?(entryId, {day, period}); isDraggable?(entry)  // HTML5 drag and drop is enabled when onDropEntry is set
```

Test hooks: cells `data-testid="cell-{day}-{period}"` with `data-day`, `data-period`, `data-empty`, `data-unavailable`; classes `data-testid="entry-{id}"` with `data-entry-id`, `data-day`, `data-period` (first period), `data-duration`, `data-conflict`; break rows `break-{period}`. Multi-period classes are one block spanning several grid rows. `UnscheduledPanel` takes `renderActions(item)` and `EntryDrawer` a `footer` for the editing step's buttons.

## Notes

* Break periods are their own numbered row (demo: 1, 2, 3, break 4, 5, 6, 7); the UI shows them as a thin "Lunch break" band.
* Every error from the API is a `{detail:{code,message}}` envelope; `ApiError.message` is safe to show to users. Rejected edits (409 `MOVE_REJECTED`) carry the full MoveResult in `ApiError.detail`.
* Data attributes and `data-testid`s are stable on purpose, for browser tests.

## Editing rules (Phase 4)

* Only **draft** versions are editable. Published / archived versions show "This version is read-only. Restore as draft to edit" with a one-click restore; nothing in the editor can send a write request for them.
* Every proposed change is dry-run on the server (`validate-move` / `validate-place`) before it can be saved; the dialog's **Save change** stays disabled while invalid. Rejected writes (409 `MOVE_REJECTED`) show the server's explanation and save nothing.
* Drag and drop: while a class is dragged every slot is dry-run in the background and painted green / red (`data-testid="drop-hint-{day}-{period}"`, `data-drop-state`). Dropping on a valid slot saves it (toast with **Undo**); on an invalid slot the **Move blocked** dialog explains why and offers alternatives. The Edit dialog is the keyboard route.
* Availability changes never modify a version. The Configure page lists how many classes now need review per version; published versions are fixed through **Create fixed draft** (restore + edit + publish).
* Printing renders `PrintSheet` into `<body>` and calls `window.print()`; the print stylesheet (landscape A4, one timetable per page) is in `index.css`.

## Test hooks (selection)

`edit-session`, `unschedule-session`, `unschedule-confirm`, `place-session`, `edit-dialog`, `edit-day`, `edit-period`, `edit-room`, `edit-teacher`, `show-all-options`, `live-validation` (`data-state` idle|checking|valid|blocked), `validation-ok`, `validation-blocked`, `blocking-conflict`, `affected-entry`, `suggestion-chip`, `save-change`, `cancel-edit`, `move-blocked`, `move-blocked-ok`, `move-blocked-edit`, `last-change`, `undo-change`, `toast-undo`, `toast-change-saved`, `readonly-banner`, `restore-as-draft`, `needs-review-banner`, `create-fixed-draft`, `goto-publish`, `print-timetable`; Versions page: `published-banner`, `versions-list`, `version-row-{id}` (+ `data-status`), `validate-version`, `publish-version`, `restore-version`, `compare-version`, `delete-version`, `delete-confirm`, `publish-dialog`, `publish-report`, `incomplete-warning`, `ack-incomplete`, `publish-confirm`, `compare-from`, `compare-to`, `compare-run`, `compare-result`, `compare-change`, `export-csv`, `export-pdf-batch|teacher|room`, `export-entity`, `export-pdf-entity`, `print-versions`; Insights: `insights-version-picker`, `teacher-bars`, `room-bars`, `batch-bars`, `insight-note`.
