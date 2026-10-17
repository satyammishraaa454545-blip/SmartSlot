"""Scheduler behaviour: feasible / infeasible data, limits, determinism, explanations."""

from __future__ import annotations

import time

import pytest

from app.engine import (
    AvailabilityRule,
    Batch,
    Config,
    Dataset,
    Requirement,
    Room,
    Subject,
    Teacher,
    expand_sessions,
    generate,
    validate,
)

from .helpers import SAMPLE_DIR, load_sample, oracle_violations, periods


def _stable(result):
    """Result as plain data without the wall-clock field."""
    data = result.model_dump()
    data["stats"].pop("elapsed_ms")
    return data


# --------------------------------------------------------------------------
# Feasible demo dataset
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def feasible():
    ds = load_sample("feasible")
    return ds, generate(ds)


def test_feasible_dataset_has_documented_shape():
    ds = load_sample("feasible")
    assert (len(ds.teachers), len(ds.subjects), len(ds.batches), len(ds.rooms)) == (6, 5, 3, 4)
    assert ds.config.days == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    teaching = [p for p in ds.config.periods if not p.is_break]
    assert len(teaching) == 6 and sum(p.is_break for p in ds.config.periods) == 1
    labs = [r for r in ds.rooms if r.room_type == "lab"]
    assert len(labs) == 1 and labs[0].capacity >= max(b.student_count for b in ds.batches)
    # one classroom is too small for the biggest batch
    biggest = max(b.student_count for b in ds.batches)
    assert any(r.room_type == "classroom" and r.capacity < biggest for r in ds.rooms)


def test_feasible_completes_with_zero_conflicts(feasible):
    ds, result = feasible
    assert result.status == "complete"
    assert result.unscheduled == []
    assert result.validation.valid and result.validation.complete
    assert result.validation.conflicts == []
    assert len(result.scheduled) == len(expand_sessions(ds))
    assert result.stats.hit_limit is False
    assert result.stats.scheduled_count == result.stats.total_sessions
    assert "no conflicts" in result.message


def test_result_round_trips_through_json(feasible):
    """Phase 2 stores/returns results as JSON; nothing may be lost on the way."""
    from app.engine import Entry, ScheduleResult

    _, result = feasible
    again = ScheduleResult.model_validate_json(result.model_dump_json())
    assert again == result
    payload = result.scheduled[0].model_dump()
    assert payload["entry_id"] == payload["session_id"]
    assert Entry.model_validate(payload) == result.scheduled[0]


def test_feasible_is_fast():
    ds = load_sample("feasible")
    t0 = time.perf_counter()
    generate(ds)
    assert time.perf_counter() - t0 < 3.0


def test_feasible_independent_oracle_agrees(feasible):
    ds, result = feasible
    assert oracle_violations(ds, result.scheduled) == []
    # and the engine's validator, run again from scratch, agrees
    assert validate(ds, result.scheduled).conflicts == []


def test_every_entry_respects_requirements(feasible):
    ds, result = feasible
    sessions = {s.session_id: s for s in expand_sessions(ds)}
    assert {e.session_id for e in result.scheduled} == set(sessions)
    rooms = {r.room_id: r for r in ds.rooms}
    batches = {b.batch_id: b for b in ds.batches}
    subjects = {s.subject_id: s for s in ds.subjects}
    teaching = {p.period for p in ds.config.periods if not p.is_break}
    off = {(a.resource_id, a.day, a.period) for a in ds.availability if not a.available}
    for e in result.scheduled:
        s = sessions[e.session_id]
        assert (e.teacher_id, e.duration) == (s.teacher_id, s.duration)
        span = list(range(e.start_period, e.start_period + e.duration))
        assert all(p in teaching for p in span), "must stay on teaching periods (no break, contiguous)"
        assert span == sorted(span) and span[-1] - span[0] == len(span) - 1
        assert all((e.teacher_id, e.day, p) not in off for p in span)
        assert all((e.room_id, e.day, p) not in off for p in span)
        assert rooms[e.room_id].capacity >= batches[e.batch_id].student_count
        practical = subjects[e.subject_id].session_type == "practical"
        assert rooms[e.room_id].room_type == ("lab" if practical else "classroom")


def test_demo_scenario_details(feasible):
    """Sharma avoids her blocked slots, practicals use the lab for 2 periods."""
    ds, result = feasible
    for e in result.scheduled:
        if e.teacher_id == "T01":  # Dr. Sharma: not Mon P3, not Fri afternoon
            span = set(range(e.start_period, e.start_period + e.duration))
            assert not (e.day == "Mon" and 3 in span)
            assert not (e.day == "Fri" and span & {5, 6, 7})
    labs = [e for e in result.scheduled if e.subject_id == "CS291"]
    assert len(labs) == 6
    assert all(e.room_id == "LAB1" and e.duration == 2 for e in labs)
    # never a 2-period class straddling lunch (Period 4)
    assert all(not (e.start_period < 4 < e.start_period + e.duration) for e in result.scheduled)


def test_subject_sessions_are_spread_across_days(feasible):
    """Soft constraint: a subject's weekly sessions for a batch use distinct days."""
    ds, result = feasible
    groups: dict[tuple[str, str], list[str]] = {}
    for e in result.scheduled:
        groups.setdefault((e.subject_id, e.batch_id), []).append(e.day)
    for (subject, batch), days in groups.items():
        assert len(set(days)) == len(days), f"{subject}/{batch} repeats a day: {days}"


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------
def test_generation_is_deterministic():
    ds = load_sample("feasible")
    assert _stable(generate(ds)) == _stable(generate(ds))
    inf = load_sample("infeasible")
    assert _stable(generate(inf)) == _stable(generate(inf))


# --------------------------------------------------------------------------
# Infeasible demo dataset
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def infeasible():
    ds = load_sample("infeasible")
    return ds, generate(ds)


def test_infeasible_is_partial_never_complete(infeasible):
    ds, result = infeasible
    assert result.status == "partial"
    assert result.status != "complete"
    assert result.validation.valid, "what was placed must still be conflict-free"
    assert not result.validation.complete
    assert result.stats.total_sessions == 66
    assert result.stats.scheduled_count == 63
    assert oracle_violations(ds, result.scheduled) == []
    assert result.stats.hit_limit is False


def test_infeasible_reports_the_precise_cause(infeasible):
    _, result = infeasible
    assert sorted(u.session.session_id for u in result.unscheduled) == [
        "CS291-CE-A-4",
        "CS291-CE-B-4",
        "CS291-CE-C-4",
    ]
    for u in result.unscheduled:
        text = " ".join(u.reasons)
        assert "Mr. Das" in text and "9" in text and "12" in text
        assert "laboratory" in text.lower()
        assert u.hints, "every unscheduled session carries a fix hint"
        assert set(u.reason_codes) <= {"TEACHER_OVERLOAD", "ROOM_OVERLOAD"}
    assert any("Computer Lab 1" in f for f in result.findings)
    assert "not found within" not in result.message  # that wording is only for search limits


def test_infeasible_missing_sessions_match_validator(infeasible):
    _, result = infeasible
    missing = sorted(c.entry_ids[0] for c in result.validation.conflicts if c.code == "MISSING_SESSION")
    assert missing == sorted(u.session.session_id for u in result.unscheduled)


# --------------------------------------------------------------------------
# Search limit
# --------------------------------------------------------------------------
def test_search_limit_reports_not_found_without_claiming_infeasibility():
    ds = load_sample("feasible")
    result = generate(ds, max_nodes=5)
    assert result.stats.hit_limit is True
    assert result.status in ("partial", "failed")
    assert result.status != "complete"
    assert "No complete solution found within the search limit" in result.message
    lowered = result.message.lower()
    for forbidden in ("infeasible", "impossible", "cannot be scheduled", "no complete timetable exists"):
        assert forbidden not in lowered
    assert result.unscheduled, "the unplaced sessions are listed"
    assert all("SEARCH_LIMIT" in u.reason_codes for u in result.unscheduled)
    assert all("may still exist" in " ".join(u.reasons) for u in result.unscheduled)
    # whatever was placed is still valid
    assert result.validation.valid
    assert oracle_violations(ds, result.scheduled) == []


def test_time_limit_is_honoured():
    ds = load_sample("feasible")
    result = generate(ds, time_limit_s=0.0)
    assert result.stats.hit_limit is True and result.status != "complete"


# --------------------------------------------------------------------------
# Static analysis on synthetic data
# --------------------------------------------------------------------------
def _dataset(
    *,
    teachers=1,
    batches=1,
    sessions=1,
    duration=1,
    kind="lecture",
    rooms=None,
    batch_size=30,
    availability=(),
    period_spec="1 2 3 4 5 6",
    days=("Mon", "Tue", "Wed", "Thu", "Fri"),
):
    """N teachers x N batches, each pair teaching one subject ``sessions`` times."""
    ts = [Teacher(teacher_id=f"T{i}", name=f"Teacher {i}") for i in range(teachers)]
    bs = [Batch(batch_id=f"B{i}", name=f"Batch {i}", student_count=batch_size) for i in range(batches)]
    return Dataset(
        teachers=ts,
        batches=bs,
        subjects=[Subject(subject_id="S", name="Subject S", session_type="practical" if kind == "lab" else "lecture")],
        rooms=rooms
        if rooms is not None
        else [Room(room_id=f"R{i}", name=f"Room {i}", capacity=100, room_type="lab" if kind == "lab" else "classroom") for i in range(batches)],
        requirements=[
            Requirement(subject_id="S", batch_id=b.batch_id, teacher_id=ts[i % teachers].teacher_id, sessions_per_week=sessions, duration=duration)
            for i, b in enumerate(bs)
        ],
        availability=[AvailabilityRule(resource_id=r, day=d, period=p, available=False) for r, d, p in availability],
        config=Config(days=list(days), periods=periods(period_spec)),
    )


def test_teacher_overload_is_detected_and_explained():
    # one teacher, three batches x 12 sessions = 36 periods, only 5 x 6 = 30 exist
    ds = _dataset(teachers=1, batches=3, sessions=12)
    result = generate(ds)
    assert result.status == "partial"
    assert result.stats.scheduled_count == 30
    assert len(result.unscheduled) == 6
    assert any("needs 36 periods per week but only 30 exist" in f for f in result.findings)
    for u in result.unscheduled:
        assert "TEACHER_OVERLOAD" in u.reason_codes
        assert "Teacher 0 needs 36 periods per week but only 30 exist." in u.reasons
    assert result.validation.valid


def test_shortfall_is_spread_fairly_over_requirements():
    ds = _dataset(teachers=1, batches=3, sessions=12)
    result = generate(ds)
    per_batch = {}
    for u in result.unscheduled:
        per_batch[u.session.batch_id] = per_batch.get(u.session.batch_id, 0) + 1
    assert per_batch == {"B0": 2, "B1": 2, "B2": 2}


def test_teacher_availability_shortfall_wording():
    off = [("T0", d, p) for d in ("Mon", "Tue", "Wed", "Thu", "Fri") for p in (4, 5, 6)]  # free: 15
    ds = _dataset(teachers=1, batches=1, sessions=20, availability=off)
    result = generate(ds)
    assert result.stats.scheduled_count == 15
    assert any("is available for only 15 of the 30 teaching periods" in f for f in result.findings)


def test_batch_overload():
    ds = _dataset(teachers=2, batches=1, sessions=31)  # 31 > 30 periods; teachers fine? one teacher index 0 only
    result = generate(ds)
    assert result.status == "partial"
    assert any("needs 31 periods per week but only 30 teaching periods exist" in f for f in result.findings)


def test_lab_block_overload_catches_consecutive_period_limit():
    """24 of 30 lab periods look fine by counting, but runs of 3 periods only
    hold one 2-period block each: 2 blocks/day x 5 days = 10 < 12 sessions."""
    ds = _dataset(
        teachers=3,
        batches=3,
        sessions=4,
        duration=2,
        kind="lab",
        rooms=[Room(room_id="LAB", name="The Lab", capacity=100, room_type="lab")],
        period_spec="1 2 3 B 5 6 7",
    )
    result = generate(ds)
    assert result.stats.scheduled_count == 10
    assert any("can fit at most 10 blocks of 2 consecutive periods" in f for f in result.findings)
    assert len(result.unscheduled) == 2
    assert all("ROOM_OVERLOAD" in u.reason_codes for u in result.unscheduled)
    assert result.validation.valid


def test_session_with_no_candidates_gets_exact_reason():
    # teacher unavailable at every period
    off = [("T0", d, p) for d in ("Mon", "Tue") for p in range(1, 7)]
    ds = _dataset(teachers=1, batches=1, sessions=2, days=("Mon", "Tue"), availability=off)
    result = generate(ds)
    assert result.status == "failed"
    assert result.scheduled == []
    assert all("Teacher 0 is unavailable for every possible slot in the week" in " ".join(u.reasons) for u in result.unscheduled)
    assert {c for u in result.unscheduled for c in u.reason_codes} == {"TEACHER_NEVER_FREE"}


def test_no_lab_big_enough():
    ds = _dataset(teachers=1, batches=1, sessions=1, duration=2, kind="lab", batch_size=60,
                  rooms=[Room(room_id="L", name="Small Lab", capacity=40, room_type="lab")])
    result = generate(ds)
    (u,) = result.unscheduled
    assert u.reason_codes == ["ROOM_TOO_SMALL"]
    assert "no laboratory is big enough for Batch 0 (60 students)" in u.reasons[0]
    assert "Small Lab, seats 40" in u.reasons[0]


def test_no_lab_at_all_and_no_classroom():
    ds = _dataset(teachers=1, batches=1, sessions=1, duration=2, kind="lab",
                  rooms=[Room(room_id="R", name="Room", capacity=100, room_type="classroom")])
    (u,) = generate(ds).unscheduled
    assert u.reason_codes == ["NO_SUITABLE_ROOM"]
    assert "needs a laboratory, but none is defined" in u.reasons[0]


def test_room_never_free_when_teacher_is():
    # teacher free only Mon; the only classroom is down all Monday
    off = [("T0", d, p) for d in ("Tue", "Wed", "Thu", "Fri") for p in range(1, 7)]
    off += [("R0", "Mon", p) for p in range(1, 7)]
    ds = _dataset(teachers=1, batches=1, sessions=1, availability=off)
    (u,) = generate(ds).unscheduled
    assert u.reason_codes == ["ROOM_NEVER_FREE"]
    assert "never free at a time when Teacher 0 is available" in u.reasons[0]


def test_duration_longer_than_any_teaching_block():
    ds = _dataset(teachers=1, batches=1, sessions=1, duration=4, period_spec="1 2 B 4 5")
    (u,) = generate(ds).unscheduled
    assert u.reason_codes == ["NO_TEACHING_BLOCK"]
    assert "breaks split the day" in u.reasons[0]


def test_requirement_with_unknown_teacher_is_reported_not_crashed():
    ds = _dataset(teachers=1, batches=2, sessions=2)
    ds.requirements[1] = ds.requirements[1].model_copy(update={"teacher_id": "T404"})
    result = generate(ds)
    assert result.status == "partial"
    bad = [u for u in result.unscheduled if u.reason_codes == ["INVALID_REFERENCE"]]
    assert len(bad) == 2 and "teacher 'T404' does not exist" in bad[0].reasons[0]
    assert result.stats.scheduled_count == 2


def test_empty_requirements_fail_cleanly():
    ds = _dataset(teachers=1, batches=1, sessions=1)
    ds = ds.model_copy(update={"requirements": []})
    result = generate(ds)
    assert result.status == "failed" and "no session requirements" in result.message


# --------------------------------------------------------------------------
# Search behaviour
# --------------------------------------------------------------------------
def test_latin_square_needs_real_search():
    """3 teachers x 3 batches in 3 periods of one day: only Latin squares work."""
    ds = Dataset(
        teachers=[Teacher(teacher_id=f"T{t}", name=f"Teacher {t}") for t in range(3)],
        subjects=[Subject(subject_id=f"S{t}", name=f"Subject {t}") for t in range(3)],
        batches=[Batch(batch_id=f"B{b}", name=f"Batch {b}", student_count=30) for b in range(3)],
        rooms=[Room(room_id=f"R{i}", name=f"Room {i}", capacity=50) for i in range(3)],
        requirements=[
            Requirement(subject_id=f"S{t}", batch_id=f"B{b}", teacher_id=f"T{t}", sessions_per_week=1)
            for b in range(3)
            for t in range(3)
        ],
        config=Config(days=["Mon"], periods=periods("1 2 3")),
    )
    result = generate(ds)
    assert result.status == "complete" and len(result.scheduled) == 9
    assert oracle_violations(ds, result.scheduled) == []


def test_exhausted_search_proves_unplaceable_without_hitting_limit():
    """Counting bounds pass but the two practicals both need the only lab in
    Period 1, so the full search proves they cannot both be placed."""
    ds = Dataset(
        teachers=[Teacher(teacher_id="A", name="Dr. A"), Teacher(teacher_id="B", name="Dr. B")],
        subjects=[Subject(subject_id="P", name="Practical", session_type="practical")],
        batches=[Batch(batch_id="X", name="Batch X", student_count=20), Batch(batch_id="Y", name="Batch Y", student_count=20)],
        rooms=[Room(room_id="L", name="Only Lab", capacity=50, room_type="lab")],
        requirements=[
            Requirement(subject_id="P", batch_id="X", teacher_id="A", sessions_per_week=1, duration=1),
            Requirement(subject_id="P", batch_id="Y", teacher_id="B", sessions_per_week=1, duration=1),
        ],
        availability=[AvailabilityRule(resource_id=t, day="Mon", period=2, available=False) for t in ("A", "B")],
        config=Config(days=["Mon"], periods=periods("1 2")),
    )
    result = generate(ds)
    assert result.status == "partial"
    assert result.stats.exhausted is True and result.stats.hit_limit is False
    assert result.stats.scheduled_count == 1
    (u,) = result.unscheduled
    assert u.reason_codes == ["NO_FREE_SLOT"]
    assert "checked every possible arrangement" in " ".join(u.reasons)
    assert "checked every possible arrangement" in result.message
    assert result.validation.valid


def test_sample_dirs_exist():
    for kind in ("feasible", "infeasible", "invalid"):
        assert (SAMPLE_DIR / kind).is_dir()
