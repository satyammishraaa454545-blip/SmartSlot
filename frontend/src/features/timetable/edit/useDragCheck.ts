import { useCallback, useEffect, useRef, useState } from "react";
import { versionsApi, type Day, type Entry, type MoveResult, type PeriodDef } from "../../../api";
import { slotKey, type Slot } from "../gridModel";

export type SlotCheck = "checking" | "valid" | "invalid";

const CONCURRENCY = 6;

/**
 * While a class is being dragged, dry-run every slot in the background so valid and invalid drop targets can be
 * painted green / red. The results are cached per drag, so the drop itself usually needs no extra request.
 */
export function useDragCheck(versionId: number, days: Day[], periods: PeriodDef[]) {
  const [dragging, setDragging] = useState<Entry | null>(null);
  const [checks, setChecks] = useState<ReadonlyMap<string, SlotCheck>>(new Map());
  const cache = useRef(new Map<string, MoveResult>());
  const inflight = useRef(new Map<string, Promise<MoveResult>>());
  const session = useRef(0);
  const pending = useRef(new Map<string, SlotCheck>());
  const flushTimer = useRef<number | null>(null);

  const flush = useCallback(() => {
    flushTimer.current = null;
    const batch = new Map(pending.current);
    pending.current.clear();
    setChecks((cur) => {
      const next = new Map(cur);
      batch.forEach((v, k) => next.set(k, v));
      return next;
    });
  }, []);

  const queueCheck = useCallback(
    (key: string, value: SlotCheck) => {
      pending.current.set(key, value);
      if (flushTimer.current === null) flushTimer.current = window.setTimeout(flush, 60);
    },
    [flush],
  );

  /** Result for dropping `entry` on `slot`: cached, in flight, or a fresh request. */
  const resultFor = useCallback(
    (entry: Entry, slot: Slot): Promise<MoveResult> => {
      const key = `${entry.entry_id}|${slotKey(slot.day, slot.period)}`;
      const hit = cache.current.get(key);
      if (hit) return Promise.resolve(hit);
      const running = inflight.current.get(key);
      if (running) return running;
      const mine = session.current;
      const p = versionsApi
        .validateMove(versionId, entry.entry_id, { day: slot.day, start_period: slot.period })
        .then((r) => {
          if (mine === session.current) {
            cache.current.set(key, r);
            queueCheck(slotKey(slot.day, slot.period), r.valid ? "valid" : "invalid");
          }
          return r;
        })
        .finally(() => inflight.current.delete(key));
      inflight.current.set(key, p);
      return p;
    },
    [versionId, queueCheck],
  );

  const end = useCallback(() => {
    session.current += 1;
    cache.current.clear();
    inflight.current.clear();
    pending.current.clear();
    if (flushTimer.current !== null) window.clearTimeout(flushTimer.current);
    flushTimer.current = null;
    setDragging(null);
    setChecks(new Map());
  }, []);

  const start = useCallback(
    (entry: Entry) => {
      session.current += 1;
      const mine = session.current;
      cache.current.clear();
      inflight.current.clear();
      setDragging(entry);
      const slots: Slot[] = [];
      for (const day of days) {
        for (const p of periods) {
          if (p.is_break) continue;
          if (day === entry.day && p.period === entry.start_period) continue; // where it already is
          slots.push({ day, period: p.period });
        }
      }
      const initial = new Map<string, SlotCheck>();
      slots.forEach((s) => initial.set(slotKey(s.day, s.period), "checking"));
      setChecks(initial);
      // small worker pool so 30 requests do not all hit the server at once
      const queue = [...slots];
      const worker = async () => {
        while (queue.length > 0 && mine === session.current) {
          const s = queue.shift()!;
          try {
            await resultFor(entry, s);
          } catch {
            /* a failed dry run simply stays "checking"; the drop validates again */
          }
        }
      };
      for (let i = 0; i < CONCURRENCY; i++) void worker();
    },
    [days, periods, resultFor],
  );

  useEffect(() => () => void (session.current += 1), []);

  return { dragging, checks, start, end, resultFor };
}
