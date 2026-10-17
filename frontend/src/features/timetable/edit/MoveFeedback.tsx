import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Lightbulb, Loader2 } from "lucide-react";
import type { Conflict, Entry, Suggestion } from "../../../api";
import { dayName } from "../../../lib/format";
import { CONFLICT_TITLES } from "../Panels";

/** The blocking conflicts of a dry run, each in plain English. */
export function ConflictList({ conflicts }: { conflicts: Conflict[] }) {
  return (
    <ul className="space-y-1.5" data-testid="blocking-conflicts">
      {conflicts.map((c, i) => (
        <li key={`${c.code}-${i}`} className="rounded-lg border border-red-200 bg-white px-3 py-2" data-testid="blocking-conflict" data-code={c.code}>
          <span className="text-[10.5px] font-bold uppercase tracking-wide text-red-700">{CONFLICT_TITLES[c.code] ?? c.code}</span>
          <p className="text-sm leading-snug text-slate-900">{c.message}</p>
        </li>
      ))}
    </ul>
  );
}

/** The other classes a proposed change would clash with, with a button to find them in the grid. */
export function AffectedEntries({ entries, onShow }: { entries: Entry[]; onShow?: (entry: Entry) => void }) {
  if (entries.length === 0) return null;
  return (
    <div data-testid="affected-entries">
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Classes it clashes with</p>
      <ul className="space-y-1.5">
        {entries.map((e) => (
          <li
            key={e.entry_id}
            className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5"
            data-testid="affected-entry"
            data-entry-id={e.entry_id}
          >
            <div className="min-w-0 text-[13px] leading-snug text-slate-700">
              <strong className="text-slate-900">{e.subject_name}</strong>
              <span className="text-slate-400"> · </span>
              {dayName(e.day).slice(0, 3)} {e.start_period === e.end_period ? `P${e.start_period}` : `P${e.start_period}–${e.end_period}`}
              <span className="text-slate-400"> · </span>
              {e.batch_name}
              <span className="text-slate-400"> · </span>
              {e.teacher_name}
              <span className="text-slate-400"> · </span>
              {e.room_name}
            </div>
            {onShow && (
              <button type="button" onClick={() => onShow(e)} className="shrink-0 text-xs font-semibold text-indigo-700 hover:underline" data-testid="show-in-grid">
                Show in grid
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Clickable alternative slots that fill the form (or apply directly). */
export function SuggestionChips({
  suggestions,
  onPick,
  selected,
  heading = "Suggested slots",
  hint,
  loading,
}: {
  suggestions: Suggestion[];
  onPick: (s: Suggestion) => void;
  /** a suggestion that matches the current form gets a check mark */
  selected?: (s: Suggestion) => boolean;
  heading?: string;
  hint?: string;
  loading?: boolean;
}) {
  return (
    <div data-testid="suggestions">
      <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
        <Lightbulb className="h-3.5 w-3.5 text-amber-500" aria-hidden /> {heading}
        {loading && <Loader2 className="h-3 w-3 animate-spin text-slate-400" aria-label="Looking for slots" />}
      </p>
      {suggestions.length === 0 ? (
        !loading && (
          <p className="text-sm text-slate-500" data-testid="no-suggestions">
            No conflict-free slot was found for this class.
          </p>
        )
      ) : (
        <div className="flex flex-wrap gap-2">
          {suggestions.map((s, i) => {
            const on = selected?.(s) ?? false;
            return (
              <button
                key={`${s.day}-${s.start_period}-${s.room_id}-${s.teacher_id}-${i}`}
                type="button"
                onClick={() => onPick(s)}
                data-testid="suggestion-chip"
                data-day={s.day}
                data-period={s.start_period}
                data-room={s.room_id}
                aria-pressed={on}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-left text-xs font-semibold transition-colors ${
                  on ? "border-emerald-500 bg-emerald-50 text-emerald-900" : "border-indigo-200 bg-indigo-50 text-indigo-800 hover:border-indigo-400 hover:bg-indigo-100"
                }`}
              >
                {on && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-hidden />}
                <span>
                  {s.label}
                  {s.start_time && s.end_time && <span className="ml-1 font-normal text-slate-500">{s.start_time}&ndash;{s.end_time}</span>}
                  {s.teacher_name && <span className="ml-1 font-normal text-slate-500">· {s.teacher_name}</span>}
                </span>
              </button>
            );
          })}
        </div>
      )}
      {hint && <p className="mt-1.5 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function BlockedHeading({ children }: { children: ReactNode }) {
  return (
    <p className="mb-2 flex items-start gap-2 text-sm font-semibold text-red-900">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden /> <span>{children}</span>
    </p>
  );
}
