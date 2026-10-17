"""Shared builders and an independent hard-constraint oracle for the tests."""

from __future__ import annotations

from pathlib import Path

from app.engine import (
    AvailabilityRule,
    Batch,
    Config,
    Dataset,
    Entry,
    PeriodDef,
    Requirement,
    Room,
    Subject,
    Teacher,
    load_dataset_from_dir,
)

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample_data"


def load_sample(kind: str) -> Dataset:
    return load_dataset_from_dir(SAMPLE_DIR / kind)


def periods(spec: str = "1 2 3 B 5 6") -> list[PeriodDef]:
    """``"1 2 3 B 5 6"`` -> periods 1,2,3, a break numbered 4, then 5,6."""
    out = []
    for i, tok in enumerate(spec.split(), start=1):
        out.append(PeriodDef(period=i, start=f"{8 + i:02d}:00", end=f"{8 + i:02d}:50", is_break=(tok == "B")))
    return out


def mini_dataset(
    *,
    days: tuple[str, ...] = ("Mon", "Tue"),
    period_spec: str = "1 2 3 B 5 6",
    extra_availability: tuple[tuple[str, str, int], ...] = (),
    extra_rooms: tuple[Room, ...] = (),
) -> Dataset:
    """Tiny hand-checkable dataset used by the validator tests.

    Sessions: S1-B1-1, S1-B1-2 (lecture, Dr. Sharma, CE-A), S1-B2-1 (lecture,
    Dr. Sharma, CE-B), S2-B1-1 (2-period practical, Prof. Iyer, CE-A).
    """
    return Dataset(
        name="mini",
        semester="3",
        teachers=[Teacher(teacher_id="T1", name="Dr. Sharma"), Teacher(teacher_id="T2", name="Prof. Iyer")],
        subjects=[
            Subject(subject_id="S1", name="Data Structures", session_type="lecture"),
            Subject(subject_id="S2", name="DS Lab", session_type="practical"),
        ],
        batches=[
            Batch(batch_id="B1", name="CE-A", student_count=40),
            Batch(batch_id="B2", name="CE-B", student_count=60),
        ],
        rooms=[
            Room(room_id="R1", name="Room 1", capacity=70, room_type="classroom"),
            Room(room_id="R2", name="Room 2", capacity=60, room_type="classroom"),
            Room(room_id="L1", name="Lab 1", capacity=80, room_type="lab"),
            *extra_rooms,
        ],
        requirements=[
            Requirement(subject_id="S1", batch_id="B1", teacher_id="T1", sessions_per_week=2, duration=1),
            Requirement(subject_id="S1", batch_id="B2", teacher_id="T1", sessions_per_week=1, duration=1),
            Requirement(subject_id="S2", batch_id="B1", teacher_id="T2", sessions_per_week=1, duration=2),
        ],
        availability=[
            AvailabilityRule(resource_id=r, day=d, period=p, available=False) for r, d, p in extra_availability
        ],
        config=Config(days=list(days), periods=periods(period_spec)),
    )


def entry(session_id: str, day: str, start: int, room: str, *, dur: int | None = None, teacher: str | None = None) -> Entry:
    """Build an Entry for the mini dataset (subject/batch/teacher derived from the id)."""
    subject, batch, _n = session_id.split("-")
    default_dur = 2 if subject == "S2" else 1
    default_teacher = "T2" if subject == "S2" else "T1"
    return Entry(
        session_id=session_id,
        day=day,
        start_period=start,
        duration=dur if dur is not None else default_dur,
        teacher_id=teacher or default_teacher,
        room_id=room,
        subject_id=subject,
        batch_id=batch,
    )


def valid_mini_entries() -> list[Entry]:
    return [
        entry("S1-B1-1", "Mon", 1, "R1"),
        entry("S1-B1-2", "Tue", 1, "R1"),
        entry("S1-B2-1", "Mon", 2, "R2"),
        entry("S2-B1-1", "Mon", 5, "L1"),
    ]


def oracle_violations(ds: Dataset, entries: list[Entry]) -> list[str]:
    """A deliberately naive, test-local re-check of the hard constraints.

    Returns human-readable violation strings (empty = fine).  Written
    independently of both the solver and the engine validator.
    """
    problems: list[str] = []
    teachers = {t.teacher_id for t in ds.teachers}
    rooms = {r.room_id: r for r in ds.rooms}
    batches = {b.batch_id: b for b in ds.batches}
    subjects = {s.subject_id: s for s in ds.subjects}
    pdefs = {p.period: p for p in ds.config.periods}
    off = {(a.resource_id, a.day, a.period) for a in ds.availability if not a.available}
    seen: dict[tuple[str, str, str, int], str] = {}
    for e in entries:
        if e.teacher_id not in teachers or e.room_id not in rooms:
            problems.append(f"{e.session_id}: unknown reference")
            continue
        if e.day not in ds.config.days:
            problems.append(f"{e.session_id}: bad day {e.day}")
        room, batch, subject = rooms[e.room_id], batches[e.batch_id], subjects[e.subject_id]
        if room.capacity < batch.student_count:
            problems.append(f"{e.session_id}: capacity")
        if (subject.session_type == "practical") != (room.room_type == "lab"):
            problems.append(f"{e.session_id}: room type")
        for p in range(e.start_period, e.start_period + e.duration):
            if p not in pdefs or pdefs[p].is_break:
                problems.append(f"{e.session_id}: period {p} is a break / does not exist")
            if (e.teacher_id, e.day, p) in off:
                problems.append(f"{e.session_id}: teacher unavailable {e.day} {p}")
            if (e.room_id, e.day, p) in off:
                problems.append(f"{e.session_id}: room unavailable {e.day} {p}")
            for kind, res in (("t", e.teacher_id), ("r", e.room_id), ("b", e.batch_id)):
                key = (kind, res, e.day, p)
                if key in seen:
                    problems.append(f"{e.session_id}: {kind} clash with {seen[key]} at {e.day} {p}")
                seen[key] = e.session_id
    return problems
