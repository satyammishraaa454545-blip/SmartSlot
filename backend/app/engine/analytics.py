"""Workload / utilization statistics computed from a list of entries."""

from __future__ import annotations

from collections.abc import Iterable

from .lookup import Lookup
from .models import Analytics, BatchLoad, Dataset, Entry, RoomUsage, TeacherLoad


def _pct(used: int, available: int) -> float:
    return round(100.0 * used / available, 1) if available > 0 else 0.0


def analytics(dataset: Dataset, entries: Iterable[Entry]) -> Analytics:
    """Teacher workload, room utilization and batch load.

    Utilization is relative to the teaching periods that actually exist in the
    week, minus any periods the resource is marked unavailable for.
    """
    entries = list(entries)
    lk = Lookup(dataset)
    teaching = lk.teaching_periods
    slots_per_week = len(teaching) * len(lk.days)

    def free_periods(resource_id: str) -> int:
        blocked = {(d, p) for (d, p) in lk.unavailable.get(resource_id, ()) if d in lk.day_index and p in teaching}
        return slots_per_week - len(blocked)

    def empty_days() -> dict[str, int]:
        return {d: 0 for d in lk.days}

    t_days: dict[str, dict[str, int]] = {t.teacher_id: empty_days() for t in dataset.teachers}
    r_days: dict[str, dict[str, int]] = {r.room_id: empty_days() for r in dataset.rooms}
    b_days: dict[str, dict[str, int]] = {b.batch_id: empty_days() for b in dataset.batches}
    t_sessions: dict[str, int] = {k: 0 for k in t_days}
    b_sessions: dict[str, int] = {k: 0 for k in b_days}

    for e in entries:
        for table, key in ((t_days, e.teacher_id), (r_days, e.room_id), (b_days, e.batch_id)):
            if key in table:
                table[key][e.day] = table[key].get(e.day, 0) + e.duration
        if e.teacher_id in t_sessions:
            t_sessions[e.teacher_id] += 1
        if e.batch_id in b_sessions:
            b_sessions[e.batch_id] += 1

    teachers = []
    for t in dataset.teachers:
        total = sum(t_days[t.teacher_id].values())
        avail = free_periods(t.teacher_id)
        teachers.append(
            TeacherLoad(
                teacher_id=t.teacher_id,
                name=t.name,
                sessions=t_sessions[t.teacher_id],
                periods_per_week=total,
                per_day=t_days[t.teacher_id],
                available_periods=avail,
                utilization_pct=_pct(total, avail),
            )
        )
    rooms = []
    for r in dataset.rooms:
        total = sum(r_days[r.room_id].values())
        avail = free_periods(r.room_id)
        rooms.append(
            RoomUsage(
                room_id=r.room_id,
                name=r.name,
                room_type=r.room_type,
                periods_used=total,
                available_periods=avail,
                utilization_pct=_pct(total, avail),
                per_day=r_days[r.room_id],
            )
        )
    batches = []
    for b in dataset.batches:
        total = sum(b_days[b.batch_id].values())
        batches.append(
            BatchLoad(
                batch_id=b.batch_id,
                name=b.name,
                sessions=b_sessions[b.batch_id],
                periods_per_week=total,
                per_day=b_days[b.batch_id],
                teaching_periods=slots_per_week,
                utilization_pct=_pct(total, slots_per_week),
            )
        )
    return Analytics(
        teachers=teachers,
        rooms=rooms,
        batches=batches,
        total_periods_scheduled=sum(e.duration for e in entries),
        teaching_periods_per_week=slots_per_week,
    )
