import { useState, type ReactNode } from "react";
import { AlertOctagon, CheckCircle2, ClockAlert, Lightbulb, PartyPopper } from "lucide-react";
import type { Conflict, ConflictCode, Entry, UnscheduledItem, ViewKind } from "../../api";
import { Badge, Button } from "../../components/ui";
import { dayName, plural } from "../../lib/format";

const entityOfItem = (u: UnscheduledItem, view: ViewKind) => (view === "batch" ? u.batch_id : view === "teacher" ? u.teacher_id : "");

const PAGE = 6;

/**
 * Sessions that could not be placed, with the reasons and one-line fixes from the scheduler.
 * `renderActions` lets the editing phase add buttons (for example "Place...") to each item without touching this file.
 */
export function UnscheduledPanel({
  items,
  view,
  entityId,
  total,
  renderActions,
}: {
  items: UnscheduledItem[];
  view: ViewKind;
  entityId: string;
  total: number;
  renderActions?: (item: UnscheduledItem) => ReactNode;
}) {
  const [limit, setLimit] = useState(PAGE);
  // items for the entity being viewed come first (rooms are chosen by the scheduler, so no room match)
  const relevant = (u: UnscheduledItem) => entityOfItem(u, view) === entityId;
  const sorted = [...items].sort((a, b) => Number(relevant(b)) - Number(relevant(a)));
  const shown = sorted.slice(0, limit);

  return (
    <section
      className={`rounded-2xl border-2 border-dashed ${items.length > 0 ? "border-amber-300 bg-amber-50/50" : "border-emerald-200 bg-emerald-50/40"}`}
      aria-labelledby="unscheduled-title"
      data-testid="unscheduled-panel"
      data-count={items.length}
    >
      <header className="flex items-center justify-between gap-3 px-5 pt-4">
        <h2 id="unscheduled-title" className="flex items-center gap-2 text-base font-semibold text-slate-900">
          <ClockAlert className={`h-5 w-5 ${items.length > 0 ? "text-amber-600" : "text-emerald-600"}`} aria-hidden />
          Unscheduled sessions
          <Badge tone={items.length > 0 ? "amber" : "green"} size="sm">
            {items.length}
          </Badge>
        </h2>
        {items.length > 0 && <span className="text-xs text-slate-500">{total - items.length} of {total} placed</span>}
      </header>
      <div className="px-5 pb-5 pt-3">
        {items.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-emerald-800" data-testid="unscheduled-empty">
            <PartyPopper className="h-4 w-4" aria-hidden /> Every required session has a place in the timetable.
          </p>
        ) : (
          <ul className="space-y-3">
            {shown.map((u) => (
              <li key={u.session_id} className="rounded-xl border border-amber-200 bg-white p-3.5" data-testid="unscheduled-item" data-session-id={u.session_id}>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-sm font-semibold text-slate-900">{u.subject_name}</span>
                  <span className="text-xs text-slate-500">{u.subject_id}</span>
                  {relevant(u) && <Badge tone="indigo" size="sm">This {view}</Badge>}
                  {u.subject_type === "practical" && <Badge tone="slate" size="sm">Lab</Badge>}
                </div>
                <div className="mt-0.5 text-xs text-slate-600">
                  {u.batch_name} {"·"} {u.teacher_name} {"·"} {plural(u.duration, "period")} {"·"} session {u.index} of {u.of}
                </div>
                {u.reasons.length > 0 && (
                  <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-slate-800">
                    {u.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                )}
                {u.hints.length > 0 && (
                  <div className="mt-2 flex gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
                    <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
                    <span>{u.hints.join(" ")}</span>
                  </div>
                )}
                {renderActions && <div className="mt-2.5 flex flex-wrap gap-2">{renderActions(u)}</div>}
              </li>
            ))}
          </ul>
        )}
        {items.length > PAGE && (
          <div className="mt-3 flex items-center justify-between gap-3 text-sm text-slate-600">
            <span>
              Showing {shown.length} of {items.length}
            </span>
            {limit < items.length ? (
              <Button size="sm" onClick={() => setLimit(items.length)} data-testid="unscheduled-show-all">
                Show all {items.length}
              </Button>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setLimit(PAGE)}>
                Show fewer
              </Button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

export const CONFLICT_TITLES: Record<ConflictCode, string> = {
  TEACHER_OVERLAP: "Teacher double-booked",
  ROOM_OVERLAP: "Room double-booked",
  BATCH_OVERLAP: "Batch has two classes at once",
  TEACHER_UNAVAILABLE: "Teacher not available",
  ROOM_UNAVAILABLE: "Room not available",
  ROOM_CAPACITY: "Room too small",
  ROOM_TYPE: "Wrong type of room",
  INVALID_DURATION: "Invalid length",
  OUTSIDE_WORKING_HOURS: "Outside working hours",
  BLOCKED_PERIOD: "Placed in a break",
  INVALID_REFERENCE: "Unknown teacher, room or subject",
  MISSING_SESSION: "Session missing",
};

/** Hard conflicts found by the validator, in plain English. Missing-session warnings are counted but listed under Unscheduled. */
export function ConflictsPanel({
  conflicts,
  entries,
  onSelectEntry,
  reviewIds,
}: {
  conflicts: Conflict[];
  entries: Entry[];
  onSelectEntry: (entryId: string) => void;
  /** classes flagged "needs review" because availability / room data changed after the timetable was made */
  reviewIds?: ReadonlySet<string>;
}) {
  const errors = conflicts.filter((c) => c.severity === "error");
  const warnings = conflicts.length - errors.length;
  const known = new Set(entries.map((e) => e.entry_id));

  return (
    <section
      className={`card ${errors.length > 0 ? "!border-red-300" : ""}`}
      aria-labelledby="conflicts-title"
      data-testid="conflicts-panel"
      data-count={errors.length}
    >
      <header className="flex items-center justify-between gap-3 px-5 pt-4">
        <h2 id="conflicts-title" className="flex items-center gap-2 text-base font-semibold text-slate-900">
          <AlertOctagon className={`h-5 w-5 ${errors.length > 0 ? "text-red-600" : "text-slate-400"}`} aria-hidden />
          Conflicts
          <Badge tone={errors.length > 0 ? "red" : "green"} size="sm">
            {errors.length}
          </Badge>
        </h2>
      </header>
      <div className="px-5 pb-5 pt-3">
        {errors.length === 0 ? (
          <div className="flex items-center gap-3 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-900" data-testid="conflicts-empty">
            <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" aria-hidden />
            <div>
              <p className="font-semibold">No conflicts</p>
              <p className="text-emerald-800/80">No teacher, room or batch is double-booked, and every class is in an allowed slot.</p>
            </div>
          </div>
        ) : (
          <ul className="space-y-2.5">
            {errors.map((c, i) => {
              const first = c.entry_ids.find((id) => known.has(id));
              return (
                <li key={`${c.code}-${i}`} className="rounded-xl border border-red-200 bg-red-50/60 p-3.5" data-testid="conflict-item" data-code={c.code}>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="red" size="sm">
                      {CONFLICT_TITLES[c.code] ?? c.code}
                    </Badge>
                    {c.entry_ids.some((id) => reviewIds?.has(id)) && (
                      <Badge tone="amber" size="sm" data-testid="conflict-needs-review">
                        Needs review
                      </Badge>
                    )}
                    {c.day && c.period !== null && (
                      <span className="text-xs text-slate-600">
                        {dayName(c.day)}, period {c.period}
                      </span>
                    )}
                  </div>
                  <p className="mt-1.5 text-sm text-slate-900">{c.message}</p>
                  {first && (
                    <button onClick={() => onSelectEntry(first)} className="mt-1.5 text-xs font-semibold text-indigo-700 hover:underline">
                      Show class details
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {warnings > 0 && (
          <p className="mt-3 text-xs text-slate-500">
            {plural(warnings, "missing-session note")} {warnings === 1 ? "is" : "are"} explained in the Unscheduled sessions panel.
          </p>
        )}
      </div>
    </section>
  );
}
