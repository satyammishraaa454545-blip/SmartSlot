"""Read-only indexes over a :class:`Dataset` (dictionary lookups and names).

Contains no placement logic, so both the solver and the independent validator
may use it.  Always build a fresh ``Lookup`` per call: datasets are mutable
(e.g. availability changes) and nothing is cached on the dataset itself.
"""

from __future__ import annotations

from .models import Batch, Dataset, PeriodDef, Room, Subject, Teacher


class Lookup:
    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset
        self.teachers: dict[str, Teacher] = {t.teacher_id: t for t in dataset.teachers}
        self.subjects: dict[str, Subject] = {s.subject_id: s for s in dataset.subjects}
        self.batches: dict[str, Batch] = {b.batch_id: b for b in dataset.batches}
        self.rooms: dict[str, Room] = {r.room_id: r for r in dataset.rooms}
        self.days: list[str] = list(dataset.config.days)
        self.day_index: dict[str, int] = {d: i for i, d in enumerate(self.days)}
        self.period_defs: dict[int, PeriodDef] = {p.period: p for p in dataset.config.periods}
        # resource_id -> {(day, period)} the resource is NOT available for.
        self.unavailable: dict[str, set[tuple[str, int]]] = {}
        for rule in dataset.availability:
            if not rule.available:
                self.unavailable.setdefault(rule.resource_id, set()).add((rule.day, rule.period))

    # -- display names -----------------------------------------------------
    def teacher_name(self, teacher_id: str) -> str:
        t = self.teachers.get(teacher_id)
        return t.name if t else teacher_id

    def subject_name(self, subject_id: str) -> str:
        s = self.subjects.get(subject_id)
        return s.name if s else subject_id

    def batch_name(self, batch_id: str) -> str:
        b = self.batches.get(batch_id)
        return b.name if b else batch_id

    def room_name(self, room_id: str) -> str:
        r = self.rooms.get(room_id)
        return r.name if r else room_id

    # -- calendar ------------------------------------------------------------
    @property
    def teaching_periods(self) -> list[int]:
        return sorted(p.period for p in self.period_defs.values() if not p.is_break)

    def is_unavailable(self, resource_id: str, day: str, period: int) -> bool:
        return (day, period) in self.unavailable.get(resource_id, ())

    def day_sort_key(self, day: str) -> tuple[int, str]:
        """Config order for known days, unknown day names last (alphabetical)."""
        return (self.day_index.get(day, len(self.days)), day)
