// Pure helpers for the editing UI: option lists, plain-English change descriptions, undo records.

import type { Conflict, DatasetDetail, Day, Entry, PeriodDef, Room, Suggestion, Teacher, ViewKind } from "../../../api";
import { dayName } from "../../../lib/format";

export interface SlotForm {
  day: Day;
  start: number;
  roomId: string;
  teacherId: string;
}

export const formOf = (e: Pick<Entry, "day" | "start_period" | "room_id" | "teacher_id">): SlotForm => ({
  day: e.day,
  start: e.start_period,
  roomId: e.room_id,
  teacherId: e.teacher_id,
});

export const sameForm = (a: SlotForm, b: SlotForm) => a.day === b.day && a.start === b.start && a.roomId === b.roomId && a.teacherId === b.teacherId;

export const formFromSuggestion = (s: Suggestion, fallbackTeacher: string): SlotForm => ({
  day: s.day,
  start: s.start_period,
  roomId: s.room_id,
  teacherId: s.teacher_id ?? fallbackTeacher,
});

// ------------------------------------------------------------------ option lists
export interface RoomOption {
  room: Room;
  /** right type and big enough for the batch */
  suitable: boolean;
  /** annotation shown next to the name */
  label: string;
}

export function roomOptions(dataset: DatasetDetail, subjectType: "lecture" | "practical", batchId: string): RoomOption[] {
  const students = dataset.batches.find((b) => b.batch_id === batchId)?.student_count ?? 0;
  const wanted = subjectType === "practical" ? "lab" : "classroom";
  return dataset.rooms.map((room) => {
    const typeOk = room.room_type === wanted;
    const bigEnough = room.capacity >= students;
    const notes: string[] = [];
    if (!typeOk) notes.push(subjectType === "practical" ? "not a lab" : "lab, not for lectures");
    if (!bigEnough) notes.push(`too small for ${students}`);
    const base = `${room.name} · ${room.room_type === "lab" ? "Lab" : "Classroom"} · ${room.capacity} seats`;
    return { room, suitable: typeOk && bigEnough, label: notes.length ? `${base} (${notes.join(", ")})` : base };
  });
}

export interface TeacherOption {
  teacher: Teacher;
  suitable: boolean;
  label: string;
}

export function teacherOptions(dataset: DatasetDetail, subjectId: string, currentTeacherId: string): TeacherOption[] {
  const teachesIt = new Set(dataset.requirements.filter((r) => r.subject_id === subjectId).map((r) => r.teacher_id));
  teachesIt.add(currentTeacherId);
  return dataset.teachers.map((teacher) => {
    const suitable = teachesIt.has(teacher.teacher_id);
    return { teacher, suitable, label: suitable ? `${teacher.name} · ${teacher.department_id}` : `${teacher.name} · ${teacher.department_id} (does not teach this subject)` };
  });
}

export const teachingPeriods = (periods: PeriodDef[]) => periods.filter((p) => !p.is_break);

export function periodLabel(p: PeriodDef): string {
  return p.is_break ? `Period ${p.period} · break ${p.start}–${p.end}` : `Period ${p.period} · ${p.start}–${p.end}`;
}

// ------------------------------------------------------------------ descriptions
const shortWhen = (e: Pick<Entry, "day" | "start_period" | "end_period">) =>
  `${e.day} ${e.start_period === e.end_period ? `P${e.start_period}` : `P${e.start_period}–${e.end_period}`}`;

export interface ChangeSummary {
  /** "CS201 · CE-A moved Mon P1 → Tue P3" */
  headline: string;
  /** timetables whose content changed: where to look */
  affects: { view: ViewKind; id: string; name: string; role: string }[];
}

/** Plain-English description of what an edit changed (before/after are the class before and after). */
export function describeChange(before: Entry | null, after: Entry | null): ChangeSummary {
  if (!before && !after) return { headline: "The timetable was updated", affects: [] };
  const ref = (before ?? after)!;
  const who = `${ref.subject_id} · ${ref.batch_name}`;
  const affects: ChangeSummary["affects"] = [];
  const add = (view: ViewKind, id: string, name: string, role: string) => {
    if (!affects.some((a) => a.view === view && a.id === id)) affects.push({ view, id, name, role });
  };

  if (before && after) {
    const parts: string[] = [];
    if (before.day !== after.day || before.start_period !== after.start_period || before.end_period !== after.end_period) {
      parts.push(`moved ${shortWhen(before)} → ${shortWhen(after)}`);
    }
    if (before.room_id !== after.room_id) parts.push(`${parts.length ? "now in" : "moved to"} ${after.room_name} (was ${before.room_name})`);
    if (before.teacher_id !== after.teacher_id) parts.push(`${parts.length ? "now taught by" : "reassigned to"} ${after.teacher_name} (was ${before.teacher_name})`);
    add("batch", after.batch_id, after.batch_name, "batch");
    add("teacher", after.teacher_id, after.teacher_name, "teacher");
    if (before.teacher_id !== after.teacher_id) add("teacher", before.teacher_id, before.teacher_name, "previous teacher");
    add("room", after.room_id, after.room_name, "room");
    if (before.room_id !== after.room_id) add("room", before.room_id, before.room_name, "previous room");
    return { headline: `${who} ${parts.join(", ") || "was updated"}`, affects };
  }
  if (after) {
    add("batch", after.batch_id, after.batch_name, "batch");
    add("teacher", after.teacher_id, after.teacher_name, "teacher");
    add("room", after.room_id, after.room_name, "room");
    return { headline: `${who} placed on ${shortWhen(after)} in ${after.room_name} with ${after.teacher_name}`, affects };
  }
  add("batch", ref.batch_id, ref.batch_name, "batch");
  add("teacher", ref.teacher_id, ref.teacher_name, "teacher");
  add("room", ref.room_id, ref.room_name, "room");
  return { headline: `${who} removed from ${shortWhen(ref)} and moved to the unscheduled list`, affects };
}

/** Where to look in the grid for a clashing class: the timetable that shows the clash best. */
export function viewForClash(entry: Entry, conflicts: Conflict[]): { view: ViewKind; id: string } {
  const c = conflicts.find((x) => x.entry_ids.includes(entry.entry_id));
  if (c?.code === "TEACHER_OVERLAP" || c?.code === "TEACHER_UNAVAILABLE") return { view: "teacher", id: entry.teacher_id };
  if (c?.code === "ROOM_OVERLAP" || c?.code === "ROOM_UNAVAILABLE") return { view: "room", id: entry.room_id };
  return { view: "batch", id: entry.batch_id };
}

export const slotText = (day: Day, period: number) => `${dayName(day)}, Period ${period}`;
