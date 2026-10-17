// Pure helpers behind the weekly grid: filtering entries for a view and computing where each block sits.

import type { AvailabilityRule, Day, Entry, PeriodDef, ViewKind } from "../../api";

export interface Slot {
  day: Day;
  period: number;
}

export interface UnavailableSlot extends Slot {
  /** shown in the tooltip, e.g. "Dr. Sharma unavailable" */
  label: string;
}

/** The id of the batch / teacher / room an entry belongs to for a given view. */
export function entityIdOf(entry: Entry, view: ViewKind): string {
  return view === "batch" ? entry.batch_id : view === "teacher" ? entry.teacher_id : entry.room_id;
}

export function entriesForView(entries: Entry[], view: ViewKind, entityId: string): Entry[] {
  return entries.filter((e) => entityIdOf(e, view) === entityId);
}

/** Availability rules for one teacher/room as hatched grid slots. */
export function unavailableSlots(rules: AvailabilityRule[], resourceId: string, name: string): UnavailableSlot[] {
  return rules
    .filter((r) => r.resource_id === resourceId)
    .map((r) => ({ day: r.day, period: r.period, label: `${name} unavailable` }));
}

export interface PlacedEntry {
  entry: Entry;
  /** 1-based CSS grid column (after the time column) */
  col: number;
  /** 1-based CSS grid row (after the header row) */
  row: number;
  /** number of grid rows covered (>1 for multi-period classes) */
  span: number;
  /** side-by-side position when several classes overlap in the same slot (only happens in invalid timetables) */
  lane: number;
  lanes: number;
}

export interface GridLayout {
  placed: PlacedEntry[];
  /** classes that do not fit the current days/periods (for example after the schedule was edited) */
  offGrid: Entry[];
  /** "day|period" keys covered by at least one class */
  occupied: Set<string>;
}

export const slotKey = (day: Day, period: number) => `${day}|${period}`;

export function layoutEntries(entries: Entry[], days: Day[], periods: PeriodDef[]): GridLayout {
  const rowOf = new Map(periods.map((p, i) => [p.period, i]));
  const colOf = new Map(days.map((d, i) => [d, i]));
  const placed: PlacedEntry[] = [];
  const offGrid: Entry[] = [];
  const occupied = new Set<string>();

  for (const entry of entries) {
    const r0 = rowOf.get(entry.start_period);
    const r1 = rowOf.get(entry.end_period);
    const c = colOf.get(entry.day);
    if (r0 === undefined || r1 === undefined || c === undefined || r1 < r0) {
      offGrid.push(entry);
      continue;
    }
    placed.push({ entry, col: c + 1, row: r0 + 1, span: r1 - r0 + 1, lane: 0, lanes: 1 });
    for (let i = r0; i <= r1; i++) occupied.add(slotKey(entry.day, periods[i].period));
  }

  // Lane assignment: overlapping classes in one day column are placed side by side.
  const byCol = new Map<number, PlacedEntry[]>();
  for (const p of placed) byCol.set(p.col, [...(byCol.get(p.col) ?? []), p]);
  for (const list of byCol.values()) {
    list.sort((a, b) => a.row - b.row || b.span - a.span);
    let cluster: PlacedEntry[] = [];
    let clusterEnd = -1;
    const laneEnds: number[] = [];
    const flush = () => {
      const lanes = Math.max(1, laneEnds.length);
      for (const p of cluster) p.lanes = lanes;
      cluster = [];
      laneEnds.length = 0;
      clusterEnd = -1;
    };
    for (const p of list) {
      if (cluster.length > 0 && p.row > clusterEnd) flush();
      let lane = laneEnds.findIndex((end) => end < p.row);
      if (lane === -1) {
        lane = laneEnds.length;
        laneEnds.push(0);
      }
      laneEnds[lane] = p.row + p.span - 1;
      p.lane = lane;
      cluster.push(p);
      clusterEnd = Math.max(clusterEnd, p.row + p.span - 1);
    }
    if (cluster.length > 0) flush();
  }

  return { placed, offGrid, occupied };
}
