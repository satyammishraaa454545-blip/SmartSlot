import { History, Undo2, X } from "lucide-react";
import type { Summary, ViewKind } from "../../../api";
import { Button } from "../../../components/ui";
import { ValidationBadge } from "../../../components/status/StatusBadges";
import type { ChangeSummary } from "./helpers";

export interface LastChange {
  id: number;
  versionId: number;
  summary: ChangeSummary;
  validation: Summary;
  at: number;
  /** reverses the change (null once it was used or is no longer possible) */
  undo: (() => Promise<void>) | null;
}

const ROLE_LABEL: Record<ViewKind, string> = { batch: "Batch", teacher: "Teacher", room: "Room" };

/** "Last change" summary: what moved, whose timetable it touches, the validation result, and an Undo. */
export function LastChangeCard({
  change,
  onUndo,
  undoing,
  onDismiss,
  onShowEntity,
}: {
  change: LastChange;
  onUndo: () => void;
  undoing: boolean;
  onDismiss: () => void;
  onShowEntity: (view: ViewKind, id: string) => void;
}) {
  const time = new Date(change.at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return (
    <section className="card border-indigo-200 !bg-indigo-50/40 px-5 py-4" aria-label="Last change" data-testid="last-change">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white">
          <History className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-700">Last change · {time}</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-900" data-testid="last-change-text">
            {change.summary.headline}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-sm text-slate-600">
            <span className="font-medium">Affects:</span>
            {change.summary.affects.map((a) => (
              <button
                key={`${a.view}-${a.id}`}
                type="button"
                onClick={() => onShowEntity(a.view, a.id)}
                className="rounded-full border border-indigo-200 bg-white px-2.5 py-0.5 text-xs font-semibold text-indigo-800 hover:border-indigo-400 hover:bg-indigo-50"
                title={`Open the ${ROLE_LABEL[a.view].toLowerCase()} timetable of ${a.name}`}
                data-testid="last-change-affects"
              >
                {a.name} <span className="font-normal text-slate-500">({a.role})</span>
              </button>
            ))}
          </div>
          <div className="mt-2 flex items-center gap-2 text-sm text-slate-600">
            Timetable now: <ValidationBadge summary={change.validation} size="sm" />
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {change.undo && (
            <Button size="sm" icon={<Undo2 className="h-4 w-4" aria-hidden />} onClick={onUndo} loading={undoing} data-testid="undo-change">
              Undo
            </Button>
          )}
          <button onClick={onDismiss} aria-label="Dismiss the last-change summary" className="rounded-lg p-1.5 text-slate-400 hover:bg-white hover:text-slate-600">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    </section>
  );
}
