import { useEffect } from "react";
import { createPortal } from "react-dom";
import type { DatasetDetail, VersionDetail, ViewKind } from "../../api";
import { formatDateTime } from "../../lib/format";
import { makeColorOf } from "../timetable/colors";
import { entityOptions, VIEW_LABEL } from "../timetable/entities";
import { entriesForView, unavailableSlots } from "../timetable/gridModel";
import { TimetableGrid } from "../timetable/TimetableGrid";

interface Props {
  version: VersionDetail;
  dataset: DatasetDetail;
  view: ViewKind;
  /** which batches / teachers / rooms to print; empty = all of them (one per page) */
  entityIds: string[];
  /** called after the print dialog closed */
  onDone: () => void;
}

/**
 * A clean print layout: one timetable per page, no navigation or buttons. It is rendered into <body> (hidden on screen)
 * and the print stylesheet (index.css) hides the rest of the app while it exists. Opens the browser's print dialog.
 */
export function PrintSheet({ version, dataset, view, entityIds, onDone }: Props) {
  const colorOf = makeColorOf(dataset.subjects.map((s) => s.subject_id));
  const all = entityOptions(dataset, view);
  const chosen = entityIds.length > 0 ? all.filter((o) => entityIds.includes(o.id)) : all;
  const { days, periods } = version.dataset;
  const incomplete = version.summary.unscheduled > 0;

  useEffect(() => {
    const done = () => onDone();
    window.addEventListener("afterprint", done, { once: true });
    // let the browser lay the sheet out first
    const t = window.setTimeout(() => window.print(), 250);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("afterprint", done);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return createPortal(
    <div className="print-sheet" data-testid="print-sheet" data-count={chosen.length}>
      {chosen.map((ent) => {
        const subjects = Array.from(new Map(entriesForView(version.entries, view, ent.id).map((e) => [e.subject_id, e.subject_name])));
        return (
          <section key={ent.id} className="print-page" data-testid="print-page" data-entity={ent.id}>
            <header className="mb-3 flex items-end justify-between gap-6 border-b-2 border-slate-800 pb-2">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  SmartSlot · {dataset.name} · Semester {dataset.semester || "-"}
                </p>
                <h1 className="text-2xl font-bold text-slate-900">
                  {VIEW_LABEL[view].one}: {ent.name} <span className="text-sm font-normal text-slate-500">{ent.detail}</span>
                </h1>
              </div>
              <div className="text-right text-xs text-slate-600">
                <p className="font-semibold text-slate-900">
                  {version.label} · {version.status_label.toUpperCase()}
                </p>
                {incomplete && <p className="font-bold text-amber-700">INCOMPLETE: {version.summary.unscheduled} session(s) not scheduled</p>}
                <p>
                  Generated {formatDateTime(version.created_at)} · printed {new Date().toLocaleDateString()}
                </p>
              </div>
            </header>
            <TimetableGrid
              days={days}
              periods={periods}
              entries={version.entries}
              view={view}
              entityId={ent.id}
              colorOf={colorOf}
              unavailable={view !== "batch" ? unavailableSlots(dataset.availability, ent.id, ent.name) : []}
              compact
            />
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-600">
              {subjects.map(([id, name]) => (
                <span key={id} className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: colorOf(id).accent }} />
                  {name}
                </span>
              ))}
            </div>
          </section>
        );
      })}
    </div>,
    document.body,
  );
}
