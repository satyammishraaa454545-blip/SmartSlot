import { Fragment, useMemo, useState, type CSSProperties, type DragEvent } from "react";
import { Check, X } from "lucide-react";
import type { Day, Entry, PeriodDef, ViewKind } from "../../api";
import { breakLabel, dayName, timeRange } from "../../lib/format";
import type { SubjectColor } from "./colors";
import { EntryBlock } from "./EntryBlock";
import { entriesForView, layoutEntries, slotKey, type PlacedEntry, type Slot, type UnavailableSlot } from "./gridModel";

/**
 * Weekly grid: columns = days, rows = periods (break periods are a thin band).
 *
 * The grid is a *controlled, presentational* component. It never fetches or mutates anything; the editing code
 * (features/timetable/edit) wraps it through these props:
 *  - `onEntryClick`  : a class was clicked / activated with the keyboard.
 *  - `onCellClick`   : an EMPTY slot was clicked (only then are empty cells rendered as buttons).
 *  - `onDropEntry`   : a class was dragged onto a slot or onto another class (set to enable HTML5 drag and drop).
 *  - `dragStatus`    : green / red / pending markers per slot while a class is dragged.
 *  - `highlightSlots`: slots to outline (the proposed slot, suggestions, ...). `selectedEntryId` outlines one class.
 *  - `highlightEntryIds`: classes to draw attention to (the ones a proposed change would clash with).
 * Every slot carries data-testid="cell-{day}-{period}" with data-day / data-period / data-empty / data-unavailable and
 * every class carries data-testid="entry-{id}" with data-entry-id / data-day / data-period (first period) / data-duration.
 */
export interface TimetableGridProps {
  days: Day[];
  periods: PeriodDef[];
  /** all entries of the version; the grid keeps only those of `entityId` in `view` */
  entries: Entry[];
  view: ViewKind;
  entityId: string;
  colorOf: (subjectId: string) => SubjectColor;
  /** hatched slots (a selected teacher's / room's unavailability) */
  unavailable?: UnavailableSlot[];
  /** entry ids that take part in a validation error (drawn with a red outline) */
  conflictEntryIds?: ReadonlySet<string>;
  selectedEntryId?: string | null;
  highlightSlots?: Slot[];
  onEntryClick?: (entry: Entry) => void;
  onCellClick?: (slot: Slot) => void;
  onDropEntry?: (entryId: string, target: Slot) => void;
  /** which entries can be dragged (default: all, when `onDropEntry` is provided) */
  isDraggable?: (entry: Entry) => boolean;
  /** a drag started / ended (the editor uses this to pre-validate every slot) */
  onDragStartEntry?: (entry: Entry) => void;
  onDragEndEntry?: () => void;
  /** while dragging: valid / invalid / pending marker per slot key ("Mon|3") */
  dragStatus?: ReadonlyMap<string, "checking" | "valid" | "invalid">;
  /** the class being dragged (drawn faded) */
  draggingId?: string | null;
  /** classes to draw attention to */
  highlightEntryIds?: ReadonlySet<string>;
  /** tighter rows, used for printing */
  compact?: boolean;
}

const HEADER_H = "44px";
const BREAK_H = "34px";
const ROW_H = "minmax(96px, auto)";
const ROW_H_COMPACT = "minmax(72px, auto)";

export function TimetableGrid({
  days,
  periods,
  entries,
  view,
  entityId,
  colorOf,
  unavailable = [],
  conflictEntryIds,
  selectedEntryId,
  highlightSlots = [],
  onEntryClick,
  onCellClick,
  onDropEntry,
  isDraggable,
  onDragStartEntry,
  onDragEndEntry,
  dragStatus,
  draggingId,
  highlightEntryIds,
  compact,
}: TimetableGridProps) {
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const shown = useMemo(() => entriesForView(entries, view, entityId), [entries, view, entityId]);
  const layout = useMemo(() => layoutEntries(shown, days, periods), [shown, days, periods]);
  const blocked = useMemo(() => new Map(unavailable.map((u) => [slotKey(u.day, u.period), u.label])), [unavailable]);
  const highlighted = useMemo(() => new Set(highlightSlots.map((s) => slotKey(s.day, s.period))), [highlightSlots]);
  const breaks = periods.filter((p) => p.is_break).length;

  const gridStyle: CSSProperties = {
    gridTemplateColumns: `minmax(72px, 96px) repeat(${days.length}, minmax(0, 1fr))`,
    gridTemplateRows: [HEADER_H, ...periods.map((p) => (p.is_break ? BREAK_H : compact ? ROW_H_COMPACT : ROW_H))].join(" "),
  };

  const canDrag = (e: Entry) => !!onDropEntry && (isDraggable ? isDraggable(e) : true);

  const onDragStart = (ev: DragEvent, entry: Entry) => {
    ev.dataTransfer.setData("text/plain", entry.entry_id);
    ev.dataTransfer.effectAllowed = "move";
    // start pre-validating after the browser has captured the drag image (changing the DOM inside dragstart can cancel the drag)
    if (onDragStartEntry) window.setTimeout(() => onDragStartEntry(entry), 0);
  };
  const onDragEnd = () => {
    setDropTarget(null);
    onDragEndEntry?.();
  };

  const dropProps = (slot: Slot) =>
    onDropEntry
      ? {
          onDragOver: (ev: DragEvent) => {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "move";
            setDropTarget(slotKey(slot.day, slot.period));
          },
          onDragLeave: () => setDropTarget((cur) => (cur === slotKey(slot.day, slot.period) ? null : cur)),
          onDrop: (ev: DragEvent) => {
            ev.preventDefault();
            setDropTarget(null);
            const id = ev.dataTransfer.getData("text/plain");
            if (id) onDropEntry(id, slot);
          },
        }
      : {};

  // A class block covers several grid cells: dropping on it targets the period under the pointer.
  const slotUnderPointer = (ev: DragEvent, p: PlacedEntry): Slot => {
    const rect = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    const frac = rect.height > 0 ? (ev.clientY - rect.top) / rect.height : 0;
    const idx = Math.max(0, Math.min(p.span - 1, Math.floor(frac * p.span)));
    const period = periods[Math.min(periods.length - 1, p.row - 1 + idx)];
    return { day: p.entry.day, period: period.period };
  };
  const entryDropProps = (p: PlacedEntry) =>
    onDropEntry
      ? {
          onDragOver: (ev: DragEvent) => {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "move";
            const s = slotUnderPointer(ev, p);
            setDropTarget(slotKey(s.day, s.period));
          },
          onDrop: (ev: DragEvent) => {
            ev.preventDefault();
            setDropTarget(null);
            const id = ev.dataTransfer.getData("text/plain");
            if (id) onDropEntry(id, slotUnderPointer(ev, p));
          },
        }
      : {};

  // The lunch / break band is not a bookable slot, but a class dropped on it must still be answered with the
  // server's explanation ("... cannot be held in Period 4 because it is a break"), not silently ignored.
  const breakDropProps = (period: number) =>
    onDropEntry
      ? {
          onDragOver: (ev: DragEvent) => {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "move";
          },
          onDrop: (ev: DragEvent) => {
            ev.preventDefault();
            const id = ev.dataTransfer.getData("text/plain");
            if (!id || days.length === 0) return;
            const rect = (ev.currentTarget as HTMLElement).getBoundingClientRect();
            const frac = rect.width > 0 ? (ev.clientX - rect.left) / rect.width : 0;
            const day = days[Math.max(0, Math.min(days.length - 1, Math.floor(frac * days.length)))];
            onDropEntry(id, { day, period });
          },
        }
      : {};

  // drop-target markers painted above the cells while a class is dragged
  const markers = useMemo(() => {
    if (!dragStatus || dragStatus.size === 0) return [];
    const out: { key: string; day: Day; period: number; col: number; row: number; status: "checking" | "valid" | "invalid" }[] = [];
    dragStatus.forEach((status, key) => {
      const [day, per] = key.split("|");
      const col = days.indexOf(day as Day);
      const row = periods.findIndex((p) => p.period === Number(per));
      if (col >= 0 && row >= 0) out.push({ key, day: day as Day, period: Number(per), col: col + 2, row: row + 2, status });
    });
    return out;
  }, [dragStatus, days, periods]);

  return (
    <div data-testid="timetable-grid" data-view={view} data-entity={entityId} data-dragging={draggingId ? "true" : undefined}>
      {layout.offGrid.length > 0 && (
        <p className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900" role="alert">
          {layout.offGrid.length === 1 ? "1 class is" : `${layout.offGrid.length} classes are`} outside the current days and periods and cannot be drawn here:{" "}
          {layout.offGrid.map((e) => `${e.subject_name} (${e.day} P${e.start_period})`).join(", ")}.
        </p>
      )}
      <div className="scroll-thin overflow-x-auto">
        <div className="grid min-w-[560px] gap-1.5" style={gridStyle}>
          {/* header row */}
          <div className="flex items-end pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400" style={{ gridColumn: 1, gridRow: 1 }}>
            Period
          </div>
          {days.map((d, i) => (
            <div
              key={d}
              className="flex items-center justify-center rounded-lg bg-slate-100 text-sm font-semibold text-slate-700"
              style={{ gridColumn: i + 2, gridRow: 1 }}
              data-testid={`day-header-${d}`}
            >
              <span className="hidden lg:inline">{dayName(d)}</span>
              <span className="lg:hidden">{d}</span>
            </div>
          ))}

          {/* period labels, break bands and background slots */}
          {periods.map((p, ri) => {
            const row = ri + 2;
            if (p.is_break) {
              return (
                <Fragment key={p.period}>
                  <div className="flex items-center whitespace-nowrap text-[10.5px] font-medium tabular-nums text-slate-400 lg:text-[11px]" style={{ gridColumn: 1, gridRow: row }}>
                    {timeRange(p.start, p.end)}
                  </div>
                  <div
                    className="break-band flex items-center justify-center rounded-lg border border-slate-200 text-xs font-semibold uppercase tracking-wider text-slate-500"
                    style={{ gridColumn: `2 / span ${days.length}`, gridRow: row }}
                    data-testid={`break-${p.period}`}
                    {...breakDropProps(p.period)}
                  >
                    {breakLabel(p, breaks)}
                  </div>
                </Fragment>
              );
            }
            return (
              <Fragment key={p.period}>
                <div className="flex flex-col justify-center pr-1" style={{ gridColumn: 1, gridRow: row }}>
                  <div className="text-sm font-semibold text-slate-700">Period {p.period}</div>
                  <div className="whitespace-nowrap text-[10.5px] tabular-nums text-slate-400 lg:text-[11px]">{timeRange(p.start, p.end)}</div>
                </div>
                {days.map((d, ci) => {
                  const key = slotKey(d, p.period);
                  const slot: Slot = { day: d, period: p.period };
                  const occupied = layout.occupied.has(key);
                  const off = blocked.get(key);
                  const isDrop = dropTarget === key;
                  const isHi = highlighted.has(key);
                  const base = {
                    style: { gridColumn: ci + 2, gridRow: row } as CSSProperties,
                    "data-testid": `cell-${d}-${p.period}`,
                    "data-day": d,
                    "data-period": p.period,
                    "data-empty": !occupied,
                    "data-unavailable": off ? "true" : undefined,
                  };
                  const ring = isDrop || isHi ? "ring-2 ring-indigo-500 ring-offset-1" : "";
                  if (off) {
                    return (
                      <div
                        key={key}
                        {...base}
                        tabIndex={0}
                        role="img"
                        aria-label={off}
                        data-tooltip={off}
                        {...dropProps(slot)}
                        className={`hatch group relative flex items-start justify-center rounded-lg border border-slate-300 p-1.5 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${ring}`}
                      >
                        {!occupied && <span className="rounded bg-white/85 px-1.5 py-0.5 text-[11px] font-semibold text-slate-600 shadow-sm">Unavailable</span>}
                        <span className="pointer-events-none absolute inset-x-1 top-1/2 z-20 hidden -translate-y-1/2 rounded-md bg-slate-900 px-2 py-1.5 text-center text-xs font-medium leading-tight text-white shadow-pop group-hover:block group-focus:block">
                          {off}
                        </span>
                      </div>
                    );
                  }
                  if (occupied) {
                    return <div key={key} {...base} {...dropProps(slot)} className={`rounded-lg ${ring}`} />;
                  }
                  if (onCellClick) {
                    return (
                      <button
                        key={key}
                        type="button"
                        {...base}
                        aria-label={`Empty slot, ${dayName(d)} period ${p.period}`}
                        onClick={() => onCellClick(slot)}
                        {...dropProps(slot)}
                        className={`rounded-lg border border-dashed border-slate-200 bg-white/60 text-slate-300 transition-colors hover:border-indigo-300 hover:bg-indigo-50/50 hover:text-indigo-500 ${ring}`}
                      />
                    );
                  }
                  return (
                    <div
                      key={key}
                      {...base}
                      {...dropProps(slot)}
                      className={`flex items-center justify-center rounded-lg border border-dashed border-slate-200 bg-white/60 text-[11px] font-medium text-slate-300 ${ring}`}
                    >
                      <span aria-hidden>Free</span>
                    </div>
                  );
                })}
              </Fragment>
            );
          })}

          {/* drop-target markers while dragging */}
          {markers.map((m) => (
            <div
              key={`mark-${m.key}`}
              aria-hidden
              data-testid={`drop-hint-${m.day}-${m.period}`}
              data-drop-state={m.status}
              style={{ gridColumn: m.col, gridRow: m.row }}
              className={`pointer-events-none relative z-[3] rounded-lg transition-colors ${
                m.status === "valid"
                  ? "bg-emerald-400/20 ring-2 ring-emerald-500"
                  : m.status === "invalid"
                    ? "bg-red-500/10 ring-1 ring-red-400/70"
                    : "border border-dashed border-slate-300"
              } ${dropTarget === m.key ? "!ring-4 !ring-indigo-500" : ""}`}
            >
              {m.status === "valid" && (
                <span className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-600 text-white shadow">
                  <Check className="h-3.5 w-3.5" aria-hidden />
                </span>
              )}
              {m.status === "invalid" && (
                <span className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-600/90 text-white shadow">
                  <X className="h-3.5 w-3.5" aria-hidden />
                </span>
              )}
            </div>
          ))}

          {/* scheduled classes */}
          {layout.placed.map((p) => {
            const style: CSSProperties = {
              gridColumn: p.col + 1,
              gridRow: `${p.row + 1} / span ${p.span}`,
              ...(p.lanes > 1 ? { width: `calc(${100 / p.lanes}% - 2px)`, marginLeft: `calc(${(100 / p.lanes) * p.lane}%)`, justifySelf: "start" } : {}),
            };
            return (
              <EntryBlock
                key={p.entry.entry_id}
                entry={p.entry}
                view={view}
                color={colorOf(p.entry.subject_id)}
                conflict={conflictEntryIds?.has(p.entry.entry_id)}
                selected={selectedEntryId === p.entry.entry_id}
                draggable={canDrag(p.entry)}
                dragging={draggingId === p.entry.entry_id}
                highlight={highlightEntryIds?.has(p.entry.entry_id)}
                style={style}
                onClick={onEntryClick}
                onDragStart={onDragStart}
                onDragEnd={onDragEnd}
                {...entryDropProps(p)}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
