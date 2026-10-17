import { DAY_NAMES, type Day, type PeriodDef } from "../api/types";

export const plural = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`;

const dateTimeFmt = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : dateTimeFmt.format(d);
}

export const dayName = (d: Day): string => DAY_NAMES[d] ?? d;

export const timeRange = (start: string | null, end: string | null): string =>
  start && end ? `${start}\u2013${end}` : "";

/** "Period 3" or "Periods 3-4" for a class that spans several periods. */
export function periodSpan(start: number, end: number): string {
  return start === end ? `Period ${start}` : `Periods ${start}\u2013${end}`;
}

/** Label used for a break row: "Lunch break" around midday, otherwise "Break". */
export function breakLabel(p: PeriodDef, breakCount: number): string {
  const [h] = p.start.split(":").map(Number);
  return breakCount === 1 || (h >= 11 && h <= 14) ? "Lunch break" : "Break";
}

export function minutesBetween(start: string, end: string): number {
  const [sh, sm] = start.split(":").map(Number);
  const [eh, em] = end.split(":").map(Number);
  return eh * 60 + em - (sh * 60 + sm);
}

export function addMinutes(time: string, minutes: number): string {
  const [h, m] = time.split(":").map(Number);
  const total = Math.min(23 * 60 + 59, h * 60 + m + minutes);
  const hh = String(Math.floor(total / 60)).padStart(2, "0");
  const mm = String(total % 60).padStart(2, "0");
  return `${hh}:${mm}`;
}

export const isTime = (s: string): boolean => /^([01]?\d|2[0-3]):[0-5]\d$/.test(s);
