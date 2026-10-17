import type { DatasetDetail, ViewKind } from "../../api";

export interface EntityOption {
  id: string;
  name: string;
  detail: string;
}

export const VIEW_LABEL: Record<ViewKind, { one: string; many: string }> = {
  batch: { one: "Batch", many: "Batches" },
  teacher: { one: "Teacher", many: "Teachers" },
  room: { one: "Room", many: "Rooms" },
};

/** The batches / teachers / rooms of a dataset as picker options. */
export function entityOptions(dataset: DatasetDetail, view: ViewKind): EntityOption[] {
  if (view === "batch") return dataset.batches.map((b) => ({ id: b.batch_id, name: b.name, detail: `${b.student_count} students` }));
  if (view === "teacher") return dataset.teachers.map((t) => ({ id: t.teacher_id, name: t.name, detail: t.department_id }));
  return dataset.rooms.map((r) => ({ id: r.room_id, name: r.name, detail: `${r.room_type === "lab" ? "Lab" : "Classroom"}, ${r.capacity} seats` }));
}
