import type { ReactNode } from "react";
import { AlertTriangle, CalendarDays, CheckCircle2, DoorOpen, GraduationCap, UserRound, Users } from "lucide-react";
import type { Conflict, DatasetDetail, Entry } from "../../api";
import { Badge, Drawer } from "../../components/ui";
import { dayName, periodSpan, plural, timeRange } from "../../lib/format";
import type { SubjectColor } from "./colors";

function Row({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 py-3">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500">{icon}</div>
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</div>
        <div className="mt-0.5 text-sm text-slate-900">{children}</div>
      </div>
    </div>
  );
}

interface EntryDrawerProps {
  entry: Entry | null;
  dataset: DatasetDetail | null;
  color: SubjectColor | null;
  conflicts: Conflict[];
  onClose: () => void;
  /** action buttons (for example Edit / Unschedule) added by the editing step */
  footer?: ReactNode;
}

/** Read-only details for one class. The editing step will add its actions in the `footer` slot of <Drawer>. */
export function EntryDrawer({ entry, dataset, color, conflicts, onClose, footer }: EntryDrawerProps) {
  const open = entry !== null;
  const batch = entry ? dataset?.batches.find((b) => b.batch_id === entry.batch_id) : undefined;
  const room = entry ? dataset?.rooms.find((r) => r.room_id === entry.room_id) : undefined;
  const teacher = entry ? dataset?.teachers.find((t) => t.teacher_id === entry.teacher_id) : undefined;
  const mine = entry ? conflicts.filter((c) => c.entry_ids.includes(entry.entry_id)) : [];

  return (
    <Drawer
      open={open}
      onClose={onClose}
      footer={footer}
      title={entry?.subject_name ?? "Class details"}
      subtitle={entry && `${entry.subject_id} · ${entry.subject_type === "practical" ? "Practical (lab)" : "Lecture"}`}
      data-testid="entry-drawer"
    >
      {entry && (
        <div>
          <div className="mb-2 flex flex-wrap gap-2">
            {color && <span className="h-6 w-1.5 rounded-full" style={{ backgroundColor: color.accent }} aria-hidden />}
            <Badge tone="indigo">
              {dayName(entry.day)} {"·"} {periodSpan(entry.start_period, entry.end_period)}
            </Badge>
            {entry.subject_type === "practical" && <Badge tone="slate">Lab session</Badge>}
            <Badge tone="slate">{plural(entry.duration, "period")}</Badge>
          </div>
          <div className="divide-y divide-slate-100">
            <Row icon={<CalendarDays className="h-4 w-4" aria-hidden />} label="When">
              {dayName(entry.day)}, {periodSpan(entry.start_period, entry.end_period).toLowerCase()}
              {entry.start_time && <span className="text-slate-500"> {"·"} {timeRange(entry.start_time, entry.end_time)}</span>}
            </Row>
            <Row icon={<Users className="h-4 w-4" aria-hidden />} label="Batch">
              {entry.batch_name}
              {batch && <span className="text-slate-500"> {"·"} {plural(batch.student_count, "student")}</span>}
            </Row>
            <Row icon={<UserRound className="h-4 w-4" aria-hidden />} label="Teacher">
              {entry.teacher_name}
              {teacher?.department_id && <span className="text-slate-500"> {"·"} {teacher.department_id}</span>}
            </Row>
            <Row icon={<DoorOpen className="h-4 w-4" aria-hidden />} label="Room">
              {entry.room_name}
              <span className="text-slate-500">
                {room ? ` · ${room.room_type === "lab" ? "Lab" : "Classroom"}, ${plural(room.capacity, "seat")}` : entry.room_type ? ` · ${entry.room_type}` : ""}
              </span>
            </Row>
            <Row icon={<GraduationCap className="h-4 w-4" aria-hidden />} label="Subject">
              {entry.subject_name} <span className="text-slate-500">({entry.subject_id})</span>
            </Row>
          </div>

          <div className="mt-4" data-testid="drawer-status">
            {mine.length === 0 && !entry.needs_review ? (
              <p className="flex items-center gap-2 rounded-xl bg-emerald-50 px-3.5 py-3 text-sm text-emerald-900">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" aria-hidden /> No conflicts for this class.
              </p>
            ) : (
              <div className="space-y-2 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-900">
                <p className="flex items-center gap-2 font-semibold">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" aria-hidden /> This class needs attention
                </p>
                <ul className="list-disc space-y-1 pl-5">
                  {(mine.length > 0 ? mine.map((c) => c.message) : entry.review_messages).map((m, i) => (
                    <li key={i}>{m}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <p className="mt-4 text-xs text-slate-400">Class id: {entry.entry_id}</p>
        </div>
      )}
    </Drawer>
  );
}
