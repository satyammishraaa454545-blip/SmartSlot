// Pure helpers behind the Insights page: plain-English observations computed from the analytics response.

import type { Analytics } from "../../api";
import { plural } from "../../lib/format";

type Teacher = Analytics["teachers"][number];
type Room = Analytics["rooms"][number];
type Batch = Analytics["batches"][number];

export type Flag = "most" | "least" | null;

export interface Note {
  tone: "amber" | "blue" | "green" | "slate";
  text: string;
}

const join = (names: string[]) => (names.length <= 2 ? names.join(" and ") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);

/** Which rows are the extremes (ties share the flag). Nothing is flagged when everybody is equal. */
export function extremes<T>(rows: T[], value: (r: T) => number): { most: Set<T>; least: Set<T>; max: number; min: number } {
  if (rows.length === 0) return { most: new Set(), least: new Set(), max: 0, min: 0 };
  const values = rows.map(value);
  const max = Math.max(...values);
  const min = Math.min(...values);
  if (max === min) return { most: new Set(), least: new Set(), max, min };
  return { most: new Set(rows.filter((r) => value(r) === max)), least: new Set(rows.filter((r) => value(r) === min)), max, min };
}

export function teacherNotes(teachers: Teacher[]): Note[] {
  const notes: Note[] = [];
  const active = teachers;
  if (active.length === 0) return notes;
  const { most, least, max, min } = extremes(active, (t) => t.periods_per_week);

  if (most.size > 0) {
    const names = [...most].map((t) => t.name);
    notes.push({
      tone: "amber",
      text:
        names.length === 1
          ? `${names[0]} teaches ${max} periods/week — the most of anyone.`
          : `${join(names)} each teach ${max} periods/week — the most of anyone.`,
    });
  }
  if (least.size > 0) {
    const names = [...least].map((t) => t.name);
    notes.push({
      tone: "blue",
      text:
        names.length === 1
          ? `${names[0]} has the lightest load: ${min} periods/week.`
          : `${join(names)} have the lightest load: ${min} periods/week each.`,
    });
  } else if (most.size === 0) {
    notes.push({ tone: "green", text: `Teaching is spread evenly: every teacher has ${max} periods/week.` });
  }

  const tight = active.filter((t) => t.utilization_pct >= 80);
  if (tight.length > 0) {
    notes.push({
      tone: "amber",
      text: `${join(tight.map((t) => t.name))} ${tight.length === 1 ? "is" : "are"} using ${tight.length === 1 ? "" : "at least "}${Math.round(Math.min(...tight.map((t) => t.utilization_pct)))}% of their available time, so there is little room to move classes.`,
    });
  }

  // a long single day
  let heavy: { t: Teacher; day: string; n: number } | null = null;
  for (const t of active) for (const [day, n] of Object.entries(t.per_day)) if (!heavy || n > heavy.n) heavy = { t, day, n };
  if (heavy && heavy.n >= 5) notes.push({ tone: "slate", text: `${heavy.t.name} has ${heavy.n} periods on ${heavy.day}, the busiest single day for any teacher.` });
  return notes;
}

export function roomNotes(rooms: Room[]): Note[] {
  const notes: Note[] = [];
  if (rooms.length === 0) return notes;
  const { most, least, max, min } = extremes(rooms, (r) => r.utilization_pct);
  if (most.size > 0) notes.push({ tone: "amber", text: `${join([...most].map((r) => r.name))} ${most.size === 1 ? "is" : "are"} the busiest ${most.size === 1 ? "room" : "rooms"}, used ${Math.round(max)}% of the week.` });
  if (least.size > 0) notes.push({ tone: "blue", text: `${join([...least].map((r) => r.name))} ${least.size === 1 ? "is" : "are"} used least (${Math.round(min)}%), so ${least.size === 1 ? "it has" : "they have"} spare capacity.` });
  const labs = rooms.filter((r) => r.room_type === "lab");
  if (labs.length > 0) {
    const avg = Math.round(labs.reduce((n, r) => n + r.utilization_pct, 0) / labs.length);
    notes.push({ tone: "slate", text: `${plural(labs.length, "lab")} ${labs.length === 1 ? "is" : "are"} used ${avg}% of the week on average.` });
  }
  const full = rooms.filter((r) => r.utilization_pct >= 90);
  if (full.length > 0) notes.push({ tone: "amber", text: `${join(full.map((r) => r.name))} ${full.length === 1 ? "is" : "are"} almost fully booked.` });
  return notes;
}

export function batchNotes(batches: Batch[]): Note[] {
  const notes: Note[] = [];
  if (batches.length === 0) return notes;
  const { most, least, max, min } = extremes(batches, (b) => b.periods_per_week);
  if (most.size > 0) notes.push({ tone: "amber", text: `${join([...most].map((b) => b.name))} ${most.size === 1 ? "has" : "have"} the fullest week: ${max} periods.` });
  if (least.size > 0) notes.push({ tone: "blue", text: `${join([...least].map((b) => b.name))} ${least.size === 1 ? "has" : "have"} the lightest week: ${min} periods.` });
  return notes;
}

export const average = (values: number[]): number => (values.length === 0 ? 0 : values.reduce((a, b) => a + b, 0) / values.length);
