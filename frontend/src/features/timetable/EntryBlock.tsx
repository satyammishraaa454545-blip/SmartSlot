import { AlertTriangle, DoorOpen, UserRound, Users } from "lucide-react";
import type { Entry, ViewKind } from "../../api";
import type { SubjectColor } from "./colors";
import { periodSpan, timeRange } from "../../lib/format";

interface EntryBlockProps {
  entry: Entry;
  view: ViewKind;
  color: SubjectColor;
  /** this class is part of a validation conflict */
  conflict?: boolean;
  selected?: boolean;
  draggable?: boolean;
  /** this class is being dragged right now */
  dragging?: boolean;
  /** draw attention (for example: it would clash with a proposed change) */
  highlight?: boolean;
  /** grid placement (CSS grid area) */
  style?: React.CSSProperties;
  onClick?: (entry: Entry) => void;
  onDragStart?: (e: React.DragEvent, entry: Entry) => void;
  onDragEnd?: (e: React.DragEvent, entry: Entry) => void;
  /** other classes can be dropped onto this one (the target is the period under the pointer) */
  onDragOver?: (e: React.DragEvent) => void;
  onDrop?: (e: React.DragEvent) => void;
}

export function entryTitle(e: Entry): string {
  const when = `${e.day} ${periodSpan(e.start_period, e.end_period)}${e.start_time ? ` ${timeRange(e.start_time, e.end_time)}` : ""}`;
  return `${e.subject_name} (${e.subject_id}) · ${e.teacher_name} · ${e.room_name} · ${e.batch_name} · ${when}`;
}

/** One scheduled class. Shows everything except the entity the current view is about. */
export function EntryBlock({ entry, view, color, conflict, selected, draggable, dragging, highlight, style, onClick, onDragStart, onDragEnd, onDragOver, onDrop }: EntryBlockProps) {
  const lab = entry.subject_type === "practical";
  const multi = entry.duration > 1;
  const showBatch = view !== "batch";
  const showTeacher = view !== "teacher";
  const showRoom = view !== "room";

  return (
    <button
      type="button"
      style={{ ...style, backgroundColor: color.bg, borderLeftColor: color.accent, color: color.text }}
      draggable={draggable}
      onClick={() => onClick?.(entry)}
      onDragStart={(e) => onDragStart?.(e, entry)}
      onDragEnd={(e) => onDragEnd?.(e, entry)}
      onDragOver={onDragOver}
      onDrop={onDrop}
      title={entryTitle(entry)}
      aria-label={entryTitle(entry)}
      data-testid={`entry-${entry.entry_id}`}
      data-entry-id={entry.entry_id}
      data-day={entry.day}
      data-period={entry.start_period}
      data-duration={entry.duration}
      data-subject={entry.subject_id}
      data-conflict={conflict ? "true" : undefined}
      data-needs-review={entry.needs_review ? "true" : undefined}
      data-highlight={highlight ? "true" : undefined}
      data-dragging={dragging ? "true" : undefined}
      className={`group relative z-[1] flex min-w-0 flex-col overflow-hidden rounded-lg border border-l-[5px] border-slate-200/80 px-2 py-2 text-left shadow-sm lg:px-2.5 transition-shadow hover:z-[2] hover:shadow-md focus-visible:z-[2] ${
        conflict ? "!border-red-500 ring-2 ring-red-400" : entry.needs_review ? "!border-amber-500 ring-2 ring-amber-400" : ""
      } ${highlight ? "!border-amber-500 ring-4 ring-amber-400 animate-pulse" : ""} ${selected ? "ring-2 ring-indigo-600" : ""} ${dragging ? "opacity-40" : ""} ${
        draggable ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-1.5 gap-y-1">
        <div className="min-w-[3.5rem] flex-1">
          <div className="line-clamp-2 break-words text-[12px] font-semibold leading-tight lg:text-[13px]">{entry.subject_name}</div>
          <div className="mt-0.5 truncate text-[11px] font-medium" style={{ color: color.muted }}>
            {entry.subject_id}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {lab && (
            <span
              className="rounded px-1.5 py-px text-[10px] font-bold uppercase tracking-wide text-white"
              style={{ backgroundColor: color.accent }}
              data-testid="lab-badge"
            >
              Lab
            </span>
          )}
          {!entry.needs_review && conflict && <AlertTriangle className="h-3.5 w-3.5 text-red-600" aria-label="Has a conflict" />}
        </div>
      </div>

      {entry.needs_review && (
        <div className="mt-1">
          <span
            className={`inline-flex max-w-full items-center gap-0.5 rounded px-1 py-px text-[9px] font-bold uppercase tracking-wide text-white lg:px-1.5 lg:text-[10px] ${conflict ? "bg-red-600" : "bg-amber-600"}`}
            data-testid="needs-review-chip"
          >
            <AlertTriangle className="hidden h-3 w-3 shrink-0 lg:block" aria-hidden /> Needs review
          </span>
        </div>
      )}

      <div className="mt-1.5 space-y-0.5 text-[12px] leading-tight">
        {showTeacher && (
          <div className="flex items-start gap-1 lg:items-center">
            <UserRound className="mt-px h-3 w-3 shrink-0 opacity-60 lg:mt-0" aria-hidden />
            <span className="min-w-0 break-words lg:truncate">{entry.teacher_name}</span>
          </div>
        )}
        {showRoom && (
          <div className="flex items-start gap-1 lg:items-center">
            <DoorOpen className="mt-px h-3 w-3 shrink-0 opacity-60 lg:mt-0" aria-hidden />
            <span className="min-w-0 break-words lg:truncate">{entry.room_name}</span>
          </div>
        )}
        {showBatch && (
          <div className="flex items-start gap-1 lg:items-center">
            <Users className="mt-px h-3 w-3 shrink-0 opacity-60 lg:mt-0" aria-hidden />
            <span className="min-w-0 break-words lg:truncate">{entry.batch_name}</span>
          </div>
        )}
      </div>

      {multi && entry.start_time && (
        <div className="mt-auto pt-1.5 text-[11px] font-medium tabular-nums" style={{ color: color.muted }}>
          {timeRange(entry.start_time, entry.end_time)} {"·"} {entry.duration} periods
        </div>
      )}
    </button>
  );
}
