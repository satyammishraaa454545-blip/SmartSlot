"""Cross-check the solver against exhaustive enumeration on tiny random datasets.

For every random instance (<= 6 sessions) the solver must say ``complete`` iff
a complete valid timetable exists at all (found here by brute force with the
test-local oracle).  This guards the pruning, symmetry breaking and the static
capacity analysis against ever rejecting a feasible instance, and guards the
validator/oracle agreement on whatever the solver places.
"""

from __future__ import annotations

import random

from app.engine import (
    AvailabilityRule,
    Batch,
    Config,
    Dataset,
    Entry,
    Requirement,
    Room,
    Subject,
    Teacher,
    expand_sessions,
    generate,
    suggest_slots,
    validate,
)

from .helpers import oracle_violations, periods


def random_dataset(rng: random.Random) -> Dataset:
    days = ["Mon", "Tue"][: rng.choice([1, 2])]
    spec = rng.choice(["1 2 3", "1 2 B 4", "1 2 3 4"])
    teachers = [Teacher(teacher_id=f"T{i}", name=f"T{i}") for i in range(rng.choice([1, 2, 3]))]
    batches = [
        Batch(batch_id=f"B{i}", name=f"B{i}", student_count=rng.choice([30, 50])) for i in range(rng.choice([1, 2, 3]))
    ]
    rooms = [Room(room_id=f"R{i}", name=f"R{i}", capacity=rng.choice([40, 60])) for i in range(rng.choice([1, 2]))]
    rooms.append(Room(room_id="L", name="L", capacity=rng.choice([40, 60]), room_type="lab"))
    reqs = []
    for b in batches:
        for subject in ("S", "P"):
            if rng.random() < 0.7:
                reqs.append(
                    Requirement(
                        subject_id=subject,
                        batch_id=b.batch_id,
                        teacher_id=rng.choice(teachers).teacher_id,
                        sessions_per_week=rng.choice([1, 1, 2]),
                        duration=rng.choice([1, 2]) if subject == "P" else 1,
                    )
                )
    availability = [
        AvailabilityRule(resource_id=res, day=d, period=p, available=False)
        for res in [t.teacher_id for t in teachers] + [r.room_id for r in rooms]
        for d in days
        for p in range(1, 5)
        if rng.random() < 0.25
    ]
    return Dataset(
        teachers=teachers,
        subjects=[Subject(subject_id="S", name="S"), Subject(subject_id="P", name="P", session_type="practical")],
        batches=batches,
        rooms=rooms,
        requirements=reqs,
        availability=availability,
        config=Config(days=days, periods=periods(spec)),
    )


def complete_timetable_exists(ds: Dataset) -> bool:
    sessions = expand_sessions(ds)
    last = max(p.period for p in ds.config.periods)
    options: list[list[Entry]] = []
    for s in sessions:
        opts = [
            e
            for d in ds.config.days
            for st in range(1, last + 1)
            for r in ds.rooms
            for e in [
                Entry(
                    session_id=s.session_id, day=d, start_period=st, duration=s.duration,
                    teacher_id=s.teacher_id, room_id=r.room_id, subject_id=s.subject_id, batch_id=s.batch_id,
                )
            ]
            if not oracle_violations(ds, [e])
        ]
        if not opts:
            return False
        options.append(opts)

    def rec(i: int, chosen: list[Entry]) -> bool:
        if i == len(sessions):
            return True
        return any(
            not oracle_violations(ds, chosen + [e]) and rec(i + 1, chosen + [e]) for e in options[i]
        )

    return rec(0, [])


def test_solver_agrees_with_brute_force_on_random_tiny_instances():
    rng = random.Random(2024)
    checked = 0
    statuses = set()
    for _ in range(2500):
        ds = random_dataset(rng)
        n = len(expand_sessions(ds))
        if n == 0 or n > 6:
            continue
        checked += 1
        result = generate(ds)
        statuses.add(result.status)
        # whatever is placed is valid, by two independent checkers
        assert result.validation.valid
        assert oracle_violations(ds, result.scheduled) == []
        assert validate(ds, result.scheduled).valid
        # complete <=> a complete timetable exists
        assert (result.status == "complete") == complete_timetable_exists(ds), ds.model_dump_json()
        # a session the search gave up on has no free slot left in the result
        for u in result.unscheduled:
            if "NO_FREE_SLOT" in u.reason_codes:
                assert suggest_slots(ds, result.scheduled, u.session.session_id) == []
    assert checked > 300
    assert {"complete", "partial", "failed"} <= statuses
