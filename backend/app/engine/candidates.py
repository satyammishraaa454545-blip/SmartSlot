"""Candidate slot generation and static "why is there no slot?" diagnosis.

A *candidate* for a session is a ``(day_index, start_period, room_index)``
triple that satisfies every constraint that does not depend on other sessions:
consecutive teaching periods, teacher availability, room type, room capacity
and room availability.  Constraints between sessions (overlaps) are handled by
the search.
"""

from __future__ import annotations

from dataclasses import dataclass

from .labels import day_name, period_phrase
from .lookup import Lookup
from .models import Dataset, Room, Session

Candidate = tuple[int, int, int]  # (day_index, start_period, room_index)


@dataclass(frozen=True)
class Reason:
    """A human-readable explanation with a stable code and a suggested fix."""

    code: str
    text: str
    hint: str = ""


def room_kind(session: Session) -> str:
    """Practical sessions need a lab; everything else needs a classroom."""
    return "lab" if session.session_type == "practical" else "classroom"


def kind_label(kind: str) -> str:
    return "laboratory" if kind == "lab" else "classroom"


def count_blocks(periods: list[int], duration: int) -> int:
    """How many disjoint blocks of ``duration`` consecutive periods fit."""
    total = 0
    run = 0
    prev = None
    for p in sorted(periods):
        run = run + 1 if prev is not None and p == prev + 1 else 1
        prev = p
        # count a block each time the running streak reaches a multiple of duration
        if run % duration == 0:
            total += 1
    return total


class Problem:
    """Precomputed calendar + resource view of a dataset for the solver."""

    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset
        self.lk = Lookup(dataset)
        self.days: list[str] = self.lk.days
        self.rooms: list[Room] = list(dataset.rooms)
        self.room_index: dict[str, int] = {r.room_id: i for i, r in enumerate(self.rooms)}
        self.teaching: list[int] = self.lk.teaching_periods
        self._starts: dict[int, list[int]] = {}

    # -- calendar ---------------------------------------------------------
    def starts(self, duration: int) -> list[int]:
        """Start periods from which ``duration`` consecutive teaching periods exist."""
        if duration not in self._starts:
            ok = set(self.teaching)
            self._starts[duration] = [
                s for s in self.teaching if all(s + i in ok for i in range(duration))
            ]
        return self._starts[duration]

    def is_free(self, resource_id: str, day: str, start: int, duration: int) -> bool:
        blocked = self.lk.unavailable.get(resource_id)
        if not blocked:
            return True
        return not any((day, p) in blocked for p in range(start, start + duration))

    def free_periods(self, resource_id: str) -> dict[str, list[int]]:
        """Teaching periods per day the resource is available for."""
        blocked = self.lk.unavailable.get(resource_id, set())
        return {
            day: [p for p in self.teaching if (day, p) not in blocked] for day in self.days
        }

    def free_cell_count(self, resource_id: str) -> int:
        return sum(len(v) for v in self.free_periods(resource_id).values())

    def free_block_count(self, resource_id: str, duration: int) -> int:
        return sum(count_blocks(v, duration) for v in self.free_periods(resource_id).values())

    @property
    def total_cells(self) -> int:
        return len(self.days) * len(self.teaching)

    # -- sessions -----------------------------------------------------------
    def missing_refs(self, s: Session) -> list[tuple[str, str]]:
        """``[(kind, id)]`` for references that do not exist in the data."""
        out = []
        if s.teacher_id not in self.lk.teachers:
            out.append(("teacher", s.teacher_id))
        if s.subject_id not in self.lk.subjects:
            out.append(("subject", s.subject_id))
        if s.batch_id not in self.lk.batches:
            out.append(("batch", s.batch_id))
        return out

    def eligible_rooms(self, s: Session) -> list[int]:
        """Rooms of the right type that are big enough for the session's batch."""
        batch = self.lk.batches.get(s.batch_id)
        if batch is None:
            return []
        kind = room_kind(s)
        return [
            i
            for i, r in enumerate(self.rooms)
            if r.room_type == kind and r.capacity >= batch.student_count
        ]

    def candidates(self, s: Session) -> list[Candidate]:
        """All slots for ``s`` that ignore other sessions (deterministic order)."""
        if self.missing_refs(s) or s.duration < 1:
            return []
        rooms = self.eligible_rooms(s)
        out: list[Candidate] = []
        for di, day in enumerate(self.days):
            for start in self.starts(s.duration):
                if not self.is_free(s.teacher_id, day, start, s.duration):
                    continue
                for ri in rooms:
                    if self.is_free(self.rooms[ri].room_id, day, start, s.duration):
                        out.append((di, start, ri))
        return out

    # -- diagnosis -----------------------------------------------------------
    def diagnose(self, s: Session) -> list[Reason]:
        """Explain precisely why ``s`` has no candidate slot at all."""
        lk = self.lk
        subj = lk.subject_name(s.subject_id)
        batch = lk.batch_name(s.batch_id)
        label = f"{subj} for {batch}"
        refs = self.missing_refs(s)
        if refs:
            fixes = {
                "teacher": "Add the teacher to teachers.csv or correct teacher_id in requirements.csv.",
                "subject": "Add the subject to subjects.csv or correct subject_id in requirements.csv.",
                "batch": "Add the batch to batches.csv or correct batch_id in requirements.csv.",
            }
            return [
                Reason(
                    "INVALID_REFERENCE",
                    f"{label}: the {kind} '{ident}' does not exist in the data.",
                    fixes[kind],
                )
                for kind, ident in refs
            ]
        if s.duration < 1:
            return [Reason("INVALID_DURATION", f"{label}: duration must be at least 1 period.", "Fix the duration in requirements.csv.")]

        teacher = lk.teacher_name(s.teacher_id)
        starts = self.starts(s.duration)
        if not starts:
            what = "period" if s.duration == 1 else f"{s.duration} consecutive teaching periods"
            return [
                Reason(
                    "NO_TEACHING_BLOCK",
                    f"{label}: the timetable has no {what} in a row on any day "
                    "(breaks split the day into shorter blocks).",
                    "Reduce the session duration or change the period/break configuration.",
                )
            ]
        teacher_slots = [
            (d, st) for d in self.days for st in starts if self.is_free(s.teacher_id, d, st, s.duration)
        ]
        span = "" if s.duration == 1 else f" {s.duration}-period"
        if not teacher_slots:
            return [
                Reason(
                    "TEACHER_NEVER_FREE",
                    f"{label}: {teacher} is unavailable for every possible{span} slot in the week.",
                    f"Open up some of {teacher}'s availability or assign a different teacher.",
                )
            ]
        kind = room_kind(s)
        label_kind = kind_label(kind)
        of_kind = [r for r in self.rooms if r.room_type == kind]
        if not of_kind:
            return [
                Reason(
                    "NO_SUITABLE_ROOM",
                    f"{label}: this is a {'practical' if kind == 'lab' else 'lecture'} and needs a "
                    f"{label_kind}, but none is defined.",
                    f"Add a {label_kind} to rooms.csv.",
                )
            ]
        students = lk.batches[s.batch_id].student_count
        big_enough = self.eligible_rooms(s)
        if not big_enough:
            largest = max(of_kind, key=lambda r: r.capacity)
            return [
                Reason(
                    "ROOM_TOO_SMALL",
                    f"{label}: no {label_kind} is big enough for {batch} ({students} students); "
                    f"the largest, {largest.name}, seats {largest.capacity}.",
                    f"Add a larger {label_kind}, or split the batch.",
                )
            ]
        names = ", ".join(self.rooms[i].name for i in big_enough)
        verb = "is" if len(big_enough) == 1 else "are"
        return [
            Reason(
                "ROOM_NEVER_FREE",
                f"{label}: the suitable {label_kind}{'' if len(big_enough) == 1 else 's'} ({names}) "
                f"{verb} never free at a time when {teacher} is available.",
                f"Adjust the availability of {teacher} or of the {label_kind}.",
            )
        ]

    # -- display ----------------------------------------------------------------
    def slot_phrase(self, day_index: int, start: int, duration: int) -> str:
        return f"{period_phrase(start, duration)} on {day_name(self.days[day_index])}"
