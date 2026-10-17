"""Dry-run edits, suggestions, revalidation and analytics."""

from __future__ import annotations

import copy

import pytest

from app.engine import (
    UnknownEntryError,
    UnknownSessionError,
    add_unavailability,
    analytics,
    generate,
    revalidate,
    suggest_slots,
    validate,
    validate_move,
    validate_place,
)

from .helpers import entry, load_sample, mini_dataset, valid_mini_entries


@pytest.fixture(scope="module")
def demo():
    ds = load_sample("feasible")
    return ds, generate(ds).scheduled


def _clash_target(ds, entries):
    """Find (entry to move, destination entry owned by the same teacher)."""
    by_teacher: dict[str, list] = {}
    for e in entries:
        by_teacher.setdefault(e.teacher_id, []).append(e)
    for _teacher, mine in sorted(by_teacher.items()):
        singles = [e for e in mine if e.duration == 1]
        if len(singles) >= 2:
            # move a single-period class of a *different batch* into the other's slot
            for a in singles:
                for b in singles:
                    if a.batch_id != b.batch_id:
                        return a, b
    raise AssertionError("no teacher with two single-period classes for different batches")


# --------------------------------------------------------------------------
# validate_move
# --------------------------------------------------------------------------
def test_move_into_teacher_clash_is_rejected_with_plain_english(demo):
    ds, entries = demo
    mover, blocker = _clash_target(ds, entries)
    result = validate_move(ds, entries, mover.session_id, new_day=blocker.day, new_start=blocker.start_period)
    assert result.valid is False
    codes = {c.code for c in result.conflicts}
    assert "TEACHER_OVERLAP" in codes
    overlap = next(c for c in result.conflicts if c.code == "TEACHER_OVERLAP")
    teacher_name = next(t.name for t in ds.teachers if t.teacher_id == mover.teacher_id)
    batch_name = next(b.name for b in ds.batches if b.batch_id == blocker.batch_id)
    assert f"{teacher_name} is already assigned to {batch_name} during Period {blocker.start_period}" in overlap.message
    assert result.message.startswith(teacher_name) or "already" in result.message
    assert blocker.session_id in {e.session_id for e in result.affected_entries}
    assert result.suggestions, "an alternative slot is proposed"
    assert all(c.suggestions for c in result.conflicts)


def test_every_suggestion_is_accepted_by_validate_move(demo):
    ds, entries = demo
    mover, blocker = _clash_target(ds, entries)
    result = validate_move(ds, entries, mover.session_id, new_day=blocker.day, new_start=blocker.start_period)
    assert len(result.suggestions) >= 3
    for s in result.suggestions:
        ok = validate_move(ds, entries, mover.session_id, new_day=s.day, new_start=s.start_period, new_room=s.room_id)
        assert ok.valid, (s, ok.message)
        # and the full independent validator agrees on the resulting timetable
        moved = [e for e in entries if e.session_id != mover.session_id] + [ok.entry]
        assert validate(ds, moved).valid


def test_valid_move_is_accepted(demo):
    ds, entries = demo
    mover = next(e for e in entries if e.duration == 1)
    suggestion = suggest_slots(ds, entries, mover, limit=1)[0]
    result = validate_move(ds, entries, mover.session_id, new_day=suggestion.day, new_start=suggestion.start_period, new_room=suggestion.room_id)
    assert result.valid and result.conflicts == [] and result.affected_entries == []
    assert result.entry is not None and result.entry.day == suggestion.day
    assert "safe to save" in result.message


def test_noop_move_is_valid(demo):
    ds, entries = demo
    e = entries[0]
    assert validate_move(ds, entries, e.session_id).valid


def test_move_does_not_mutate_inputs(demo):
    ds, entries = demo
    mover, blocker = _clash_target(ds, entries)
    before_entries, before_ds = copy.deepcopy(entries), ds.model_dump()
    validate_move(ds, entries, mover.session_id, new_day=blocker.day, new_start=blocker.start_period)
    suggest_slots(ds, entries, mover)
    assert entries == before_entries and ds.model_dump() == before_ds


def test_move_to_wrong_room_type_and_capacity_and_break(demo):
    ds, entries = demo
    lecture = next(e for e in entries if e.subject_id != "CS291" and e.batch_id == "CE-A")
    lab_move = validate_move(ds, entries, lecture.session_id, new_room="LAB1")
    assert not lab_move.valid and any(c.code == "ROOM_TYPE" for c in lab_move.conflicts)
    small = validate_move(ds, entries, lecture.session_id, new_room="R103")  # seats 48 < CE-A's 60
    assert any(c.code == "ROOM_CAPACITY" for c in small.conflicts)
    lunch = validate_move(ds, entries, lecture.session_id, new_start=4)
    assert any(c.code == "BLOCKED_PERIOD" for c in lunch.conflicts)


def test_move_into_unavailable_slot_names_the_teacher(demo):
    ds, entries = demo
    sharma = next(e for e in entries if e.teacher_id == "T01" and e.duration == 1)
    result = validate_move(ds, entries, sharma.session_id, new_day="Mon", new_start=3)  # Sharma is off Mon P3
    assert not result.valid
    assert any(c.code == "TEACHER_UNAVAILABLE" and "Dr. Sharma is not available during Period 3 on Monday" in c.message for c in result.conflicts)


def test_move_can_change_teacher_and_is_validated(demo):
    ds, entries = demo
    e = next(x for x in entries if x.subject_id == "CS201" and x.batch_id == "CE-A")
    # hand the class to Dr. Rao at a slot where Rao teaches CE-C: clash expected
    rao_slot = next(x for x in entries if x.teacher_id == "T06")
    result = validate_move(ds, entries, e.session_id, new_day=rao_slot.day, new_start=rao_slot.start_period, new_teacher="T06")
    assert not result.valid
    assert any(c.code == "TEACHER_OVERLAP" and "Dr. Rao" in c.message for c in result.conflicts)
    assert all(s.teacher_id == "T06" for s in result.suggestions)


def test_unknown_ids_raise():
    ds = mini_dataset()
    with pytest.raises(UnknownEntryError):
        validate_move(ds, valid_mini_entries(), "NOPE-1-1")
    with pytest.raises(UnknownSessionError):
        validate_place(ds, valid_mini_entries(), "NOPE-1-1", "Mon", 1, "R1")
    with pytest.raises(UnknownSessionError):
        suggest_slots(ds, valid_mini_entries(), "NOPE-1-1")


# --------------------------------------------------------------------------
# validate_place (unscheduled -> scheduled)
# --------------------------------------------------------------------------
def test_validate_place_valid_and_invalid():
    ds = mini_dataset()
    entries = valid_mini_entries()[:3]  # practical S2-B1-1 is unscheduled
    ok = validate_place(ds, entries, "S2-B1-1", "Tue", 5, "L1")
    assert ok.valid and ok.entry is not None and ok.entry.duration == 2 and ok.entry.teacher_id == "T2"
    # lecture room for a practical, and a batch clash
    bad = validate_place(ds, entries, "S2-B1-1", "Mon", 1, "R1")
    codes = {c.code for c in bad.conflicts}
    assert {"ROOM_TYPE", "BATCH_OVERLAP", "ROOM_OVERLAP"} <= codes
    assert bad.suggestions and all(s.room_id == "L1" for s in bad.suggestions)
    assert [e.session_id for e in entries] == ["S1-B1-1", "S1-B1-2", "S1-B2-1"]  # untouched


def test_validate_place_rejects_already_scheduled_session():
    ds = mini_dataset()
    result = validate_place(ds, valid_mini_entries(), "S1-B1-1", "Tue", 2, "R1")
    assert not result.valid and "already scheduled" in result.message


# --------------------------------------------------------------------------
# suggest_slots
# --------------------------------------------------------------------------
def test_suggest_slots_for_unscheduled_session_only_lab_two_periods():
    ds = mini_dataset()
    entries = valid_mini_entries()[:3]
    sug = suggest_slots(ds, entries, "S2-B1-1", limit=50)
    assert sug and all(s.room_id == "L1" for s in sug)
    for s in sug:  # all land on valid, non-lunch, contiguous periods
        assert s.start_period in (1, 2, 5)  # 2-period blocks never start at 3 (lunch) or 6 (last)
        trial = entries + [entry("S2-B1-1", s.day, s.start_period, s.room_id)]
        assert validate(ds, trial).conflicts == []


def test_suggest_slots_is_deterministic_and_limited():
    ds = load_sample("feasible")
    entries = generate(ds).scheduled
    target = entries[5]
    a = suggest_slots(ds, entries, target, limit=4)
    b = suggest_slots(ds, entries, target, limit=4)
    assert a == b and len(a) == 4
    assert all((s.day, s.start_period, s.room_id) != (target.day, target.start_period, target.room_id) for s in a)


# --------------------------------------------------------------------------
# revalidation after availability changes
# --------------------------------------------------------------------------
def test_revalidate_flags_entries_hit_by_new_unavailability(demo):
    ds, entries = demo
    victim = next(e for e in entries if e.teacher_id == "T02")  # Prof. Iyer
    changed = add_unavailability(ds, "T02", [(victim.day, victim.start_period)])
    assert len(ds.availability) < len(changed.availability), "original dataset is untouched"

    clean = revalidate(ds, entries)
    assert clean.needs_review == [] and clean.report.complete

    result = revalidate(changed, entries)
    assert [r.entry_id for r in result.needs_review] == [victim.session_id]
    item = result.needs_review[0]
    assert item.codes == ["TEACHER_UNAVAILABLE"]
    assert "Prof. Iyer is not available" in item.messages[0]
    assert not result.report.valid
    # the published/original entries were not altered
    assert victim in entries


def test_revalidate_flags_room_unavailability(demo):
    ds, entries = demo
    lab = next(e for e in entries if e.room_id == "LAB1")
    changed = add_unavailability(ds, "LAB1", [(lab.day, lab.start_period + 1)])
    result = revalidate(changed, entries)
    assert [r.entry_id for r in result.needs_review] == [lab.session_id]
    assert result.needs_review[0].codes == ["ROOM_UNAVAILABLE"]


def test_regenerating_after_change_avoids_the_new_unavailability(demo):
    ds, entries = demo
    victim = next(e for e in entries if e.teacher_id == "T02")
    changed = add_unavailability(ds, "T02", [(victim.day, victim.start_period)])
    fresh = generate(changed)
    assert fresh.status == "complete"
    assert not any(
        e.teacher_id == "T02" and e.day == victim.day and e.start_period <= victim.start_period < e.start_period + e.duration
        for e in fresh.scheduled
    )


# --------------------------------------------------------------------------
# analytics
# --------------------------------------------------------------------------
def test_analytics_totals(demo):
    ds, entries = demo
    a = analytics(ds, entries)
    total = sum(e.duration for e in entries)
    assert a.total_periods_scheduled == total == 66  # 54 lecture periods + 6 labs x 2
    assert sum(t.periods_per_week for t in a.teachers) == total
    assert sum(r.periods_used for r in a.rooms) == total
    assert sum(b.periods_per_week for b in a.batches) == total
    assert a.teaching_periods_per_week == 30
    sharma = next(t for t in a.teachers if t.teacher_id == "T01")
    assert sharma.periods_per_week == 10 and sharma.available_periods == 26
    assert sum(sharma.per_day.values()) == 10 and set(sharma.per_day) == set(ds.config.days)
    assert sharma.utilization_pct == round(100 * 10 / 26, 1)
    lab = next(r for r in a.rooms if r.room_id == "LAB1")
    assert lab.periods_used == 12 and lab.available_periods == 27 and lab.utilization_pct == round(100 * 12 / 27, 1)
    for b in a.batches:
        assert b.periods_per_week == 22 and b.utilization_pct == round(100 * 22 / 30, 1)


def test_analytics_empty_timetable():
    a = analytics(mini_dataset(), [])
    assert a.total_periods_scheduled == 0
    assert all(t.periods_per_week == 0 and t.utilization_pct == 0 for t in a.teachers)
