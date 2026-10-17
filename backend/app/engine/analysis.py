"""Static capacity analysis (runs before the search).

Detects resources that are asked to do more than the week can hold - a teacher
who needs 36 periods when only 30 exist, a lab that cannot fit all the
two-period practicals, a batch with more classes than teaching periods.  These
shortfalls are *provable by counting*, so the sessions that cannot fit are
removed from the search up front and explained precisely; the solver then
places everything else.

Bounds used (all sound, i.e. they never reject a requirement set that has a
valid timetable):
  * cells:  total periods needed  <=  free teaching periods in the week;
  * blocks: sessions needing >= d consecutive periods  <=  number of disjoint
    d-period blocks available (catches e.g. a lab that is free 30 periods a
    week but can only host 10 two-period practicals).
Rooms are checked per (room type, minimum capacity) pool: sessions whose batch
has at least N students can only use rooms seating at least N.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from collections.abc import Callable

from .candidates import Problem, count_blocks, kind_label, room_kind
from .models import Session

# (kind, needed, capacity, block_size) of the first violated bound.
Violation = tuple[str, int, int, int]
Check = Callable[[list[Session]], Optional[Violation]]


@dataclass
class Overload:
    """One resource asked to do more than the week allows."""

    kind: str  # "teacher" | "batch" | "room"
    code: str  # TEACHER_OVERLOAD | BATCH_OVERLOAD | ROOM_OVERLOAD
    text: str
    hint: str
    members: set[str] = field(default_factory=set)  # session ids the shortfall applies to
    check: Optional[Check] = None  # re-evaluates the bound on a subset of sessions
    group: list[Session] = field(default_factory=list)


@dataclass
class Dropped:
    reasons: list[str]
    codes: list[str]
    hints: list[str]


@dataclass
class Analysis:
    kept: list[Session]  # sessions that still go to the search
    dropped: dict[str, Dropped]  # session_id -> why it cannot be scheduled
    findings: list[Overload]  # every shortfall found


def _violation(sessions: list[Session], cells: int, blocks: Callable[[int], int]) -> Optional[Violation]:
    need = sum(s.duration for s in sessions)
    if need > cells:
        return ("cells", need, cells, 0)
    for size in sorted({s.duration for s in sessions if s.duration >= 2}):
        count = sum(1 for s in sessions if s.duration >= size)
        cap = blocks(size)
        if count > cap:
            return ("blocks", count, cap, size)
    return None


def _shed_all(findings: list[Overload], sessions: list[Session]) -> set[str]:
    """Choose sessions to drop so that every shortfall is cured.

    Greedy hitting-set: repeatedly drop the session that sits in the most
    still-violated groups (a session in both an overloaded teacher and an
    overloaded lab helps twice); ties go to the longest session (it frees the
    most periods, so fewer sessions need to go), then to the requirement with
    the most sessions left (spreads the shortfall fairly), then to the later
    requirement and its highest-numbered session so the remaining ones stay
    1..k.
    """
    dropped: set[str] = set()
    left: dict[int, int] = {}
    for s in sessions:
        left[s.requirement_index] = left.get(s.requirement_index, 0) + 1
    while True:
        score: dict[str, int] = {}
        by_id: dict[str, Session] = {}
        for f in findings:
            assert f.check is not None
            live = [s for s in f.group if s.session_id not in dropped]
            v = f.check(live)
            if v is None:
                continue
            # A blocks violation can only be cured by dropping a long-enough session.
            pool = live if v[0] == "cells" else [s for s in live if s.duration >= v[3]]
            for s in pool:
                score[s.session_id] = score.get(s.session_id, 0) + 1
                by_id[s.session_id] = s
        if not score:
            return dropped
        victim = max(
            by_id.values(),
            key=lambda s: (score[s.session_id], s.duration, left[s.requirement_index], s.requirement_index, s.index),
        )
        dropped.add(victim.session_id)
        left[victim.requirement_index] -= 1


def _periods(n: int) -> str:
    return f"{n} period{'s' if n != 1 else ''}"


def analyze(problem: Problem, sessions: list[Session]) -> Analysis:
    """Find provable capacity shortfalls among ``sessions`` (all have candidates)."""
    lk = problem.lk
    findings: list[Overload] = []

    # ---- 1. detect every shortfall on the full set --------------------------------
    by_teacher: dict[str, list[Session]] = {}
    by_batch: dict[str, list[Session]] = {}
    for s in sessions:
        by_teacher.setdefault(s.teacher_id, []).append(s)
        by_batch.setdefault(s.batch_id, []).append(s)

    for tid in sorted(by_teacher):
        cells = problem.free_cell_count(tid)

        def teacher_check(live: list[Session], tid: str = tid, cells: int = cells) -> Optional[Violation]:
            return _violation(live, cells, lambda d: problem.free_block_count(tid, d))

        group = by_teacher[tid]
        v = teacher_check(group)
        if v is None:
            continue
        name = lk.teacher_name(tid)
        if v[0] == "cells":
            if v[2] == problem.total_cells:
                text = f"{name} needs {_periods(v[1])} per week but only {v[2]} exist."
            else:
                text = (
                    f"{name} needs {_periods(v[1])} per week but is available for only {v[2]} of the "
                    f"{problem.total_cells} teaching periods."
                )
        else:
            text = (
                f"{name} needs {v[1]} sessions of {v[3]} or more consecutive periods per week, but "
                f"only {v[2]} such blocks fit in the periods {name} is available."
            )
        findings.append(
            Overload(
                "teacher",
                "TEACHER_OVERLOAD",
                text,
                f"Reduce {name}'s sessions per week, open up more availability, or give some classes to another teacher.",
                {s.session_id for s in group},
                teacher_check,
                group,
            )
        )

    def week_blocks(d: int) -> int:
        return len(problem.days) * count_blocks(problem.teaching, d)

    def batch_check(live: list[Session]) -> Optional[Violation]:
        return _violation(live, problem.total_cells, week_blocks)

    for bid in sorted(by_batch):
        group = by_batch[bid]
        v = batch_check(group)
        if v is None:
            continue
        name = lk.batch_name(bid)
        if v[0] == "cells":
            text = f"{name} needs {_periods(v[1])} per week but only {v[2]} teaching periods exist."
        else:
            text = (
                f"{name} needs {v[1]} sessions of {v[3]} or more consecutive periods per week, but "
                f"the timetable only has room for {v[2]} such blocks."
            )
        findings.append(
            Overload(
                "batch",
                "BATCH_OVERLOAD",
                text,
                f"Reduce the weekly sessions for {name} or add working days / periods.",
                {s.session_id for s in group},
                batch_check,
                group,
            )
        )

    for kind in ("lab", "classroom"):
        of_kind = [s for s in sessions if room_kind(s) == kind]
        if not of_kind:
            continue
        sizes = sorted({lk.batches[s.batch_id].student_count for s in of_kind})
        label = kind_label(kind)
        for threshold in sizes:
            group = [s for s in of_kind if lk.batches[s.batch_id].student_count >= threshold]
            pool = [
                i for i, r in enumerate(problem.rooms) if r.room_type == kind and r.capacity >= threshold
            ]
            cells = sum(problem.free_cell_count(problem.rooms[i].room_id) for i in pool)

            def pool_blocks(d: int, pool: list[int] = pool) -> int:
                return sum(problem.free_block_count(problem.rooms[i].room_id, d) for i in pool)

            def pool_check(
                live: list[Session], cells: int = cells, pool_blocks: Callable[[int], int] = pool_blocks
            ) -> Optional[Violation]:
                return _violation(live, cells, pool_blocks)

            v = pool_check(group)
            if v is None:
                continue
            names = ", ".join(problem.rooms[i].name for i in pool)
            plural = "" if len(pool) == 1 else "s"
            seats = f" seating {threshold}+ students" if threshold > sizes[0] else ""
            if v[0] == "cells":
                text = (
                    f"The {label}{plural}{seats} ({names}) can host only {_periods(v[2])} per week, "
                    f"but {_periods(v[1])} of {label} sessions are required."
                )
            else:
                text = (
                    f"The {label}{plural}{seats} ({names}) can fit at most {v[2]} "
                    f"block{'s' if v[2] != 1 else ''} of {v[3]} consecutive periods per week, "
                    f"but {v[1]} such {label} sessions are required."
                )
            findings.append(
                Overload(
                    "room",
                    "ROOM_OVERLOAD",
                    text,
                    f"Add another {label}, reduce the number of {label} sessions per week, or free up the {label}'s availability.",
                    {s.session_id for s in group},
                    pool_check,
                    group,
                )
            )

    # ---- 2. shed as few sessions as possible so every bound holds -----------------
    dropped_ids = _shed_all(findings, sessions)

    dropped: dict[str, Dropped] = {}
    for s in sessions:
        if s.session_id in dropped_ids:
            relevant = [f for f in findings if s.session_id in f.members]
            dropped[s.session_id] = Dropped(
                reasons=[f.text for f in relevant],
                codes=sorted({f.code for f in relevant}),
                hints=[f.hint for f in relevant],
            )
    kept = [s for s in sessions if s.session_id not in dropped_ids]
    return Analysis(kept=kept, dropped=dropped, findings=findings)
