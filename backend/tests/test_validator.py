"""One test per validator conflict code, built from hand-made entry lists."""

from __future__ import annotations

import copy

import pytest

from app.engine import CONFLICT_CODES, AvailabilityRule, Entry, Room, add_unavailability, validate

from .helpers import entry, mini_dataset, valid_mini_entries


def codes_of(report):
    return sorted({c.code for c in report.conflicts})


def only(report, code):
    found = [c for c in report.conflicts if c.code == code]
    assert found, f"expected {code}, got {codes_of(report)}"
    return found


def test_baseline_is_valid_and_complete():
    report = validate(mini_dataset(), valid_mini_entries())
    assert report.conflicts == []
    assert report.valid and report.complete and report.status == "valid_complete"
    assert "Valid and complete" in report.summary


def test_every_documented_code_has_a_test():
    """Guard: adding a code to CONFLICT_CODES requires adding a test below."""
    tested = {
        "TEACHER_OVERLAP", "ROOM_OVERLAP", "BATCH_OVERLAP", "TEACHER_UNAVAILABLE", "ROOM_UNAVAILABLE",
        "ROOM_CAPACITY", "ROOM_TYPE", "INVALID_DURATION", "OUTSIDE_WORKING_HOURS", "BLOCKED_PERIOD",
        "INVALID_REFERENCE", "MISSING_SESSION",
    }
    assert set(CONFLICT_CODES) == tested


def test_teacher_overlap():
    entries = valid_mini_entries()
    entries[2] = entry("S1-B2-1", "Mon", 1, "R2")  # Dr. Sharma already in CE-A at Period 1
    report = validate(mini_dataset(), entries)
    assert codes_of(report) == ["TEACHER_OVERLAP"]
    (c,) = only(report, "TEACHER_OVERLAP")
    assert c.severity == "error" and not report.valid
    assert (c.day, c.period) == ("Mon", 1)
    assert c.entry_ids == ["S1-B1-1", "S1-B2-1"]
    assert c.involved.teacher_id == "T1"
    assert "Dr. Sharma" in c.message and "CE-A" in c.message and "CE-B" in c.message
    assert "Period 1" in c.message and "Monday" in c.message


def test_summary_uses_plain_english_not_codes():
    entries = valid_mini_entries()
    entries[2] = entry("S1-B2-1", "Mon", 1, "R2")  # teacher clash
    report = validate(mini_dataset(), entries)
    assert report.summary.startswith("1 conflict must be fixed before this timetable can be published")
    assert "teacher double-booked: 1" in report.summary
    assert "TEACHER_OVERLAP" not in report.summary and " x " not in report.summary


def test_room_overlap():
    entries = valid_mini_entries()
    entries[2] = entry("S1-B2-1", "Mon", 1, "R1", teacher="T2")  # R1 used by CE-A at Period 1
    report = validate(mini_dataset(), entries)
    assert codes_of(report) == ["ROOM_OVERLAP"]
    (c,) = only(report, "ROOM_OVERLAP")
    assert c.involved.room_id == "R1" and "Room 1" in c.message and "Monday" in c.message


def test_batch_overlap():
    entries = valid_mini_entries()
    entries[3] = entry("S2-B1-1", "Mon", 1, "L1")  # CE-A already has Data Structures at Period 1
    report = validate(mini_dataset(), entries)
    assert codes_of(report) == ["BATCH_OVERLAP"]
    (c,) = only(report, "BATCH_OVERLAP")
    assert "CE-A" in c.message and "two classes at the same time" in c.message


def test_multi_period_overlap_reports_period_range():
    entries = valid_mini_entries()
    entries[3] = entry("S2-B1-1", "Mon", 1, "L1", dur=2)  # P1-2 overlaps the CE-A lecture only at P1
    entries[2] = entry("S1-B2-1", "Mon", 3, "R2")
    report = validate(mini_dataset(), entries)
    (c,) = only(report, "BATCH_OVERLAP")
    assert c.period == 1 and "Period 1 " in c.message


def test_teacher_unavailable():
    ds = mini_dataset(extra_availability=(("T1", "Tue", 1),))
    report = validate(ds, valid_mini_entries())  # S1-B1-2 is Tue P1
    assert codes_of(report) == ["TEACHER_UNAVAILABLE"]
    (c,) = only(report, "TEACHER_UNAVAILABLE")
    assert c.entry_ids == ["S1-B1-2"] and (c.day, c.period) == ("Tue", 1)
    assert "Dr. Sharma is not available during Period 1 on Tuesday" in c.message


def test_availability_true_rows_are_ignored():
    """Only available=0 rows matter; available=1 rows are accepted and ignored."""
    ds = mini_dataset()
    ds.availability.append(AvailabilityRule(resource_id="T1", day="Tue", period=1, available=True))
    assert validate(ds, valid_mini_entries()).conflicts == []


def test_room_unavailable_multi_period():
    ds = mini_dataset(extra_availability=(("L1", "Mon", 6),))
    report = validate(ds, valid_mini_entries())  # lab practical is Mon P5-6
    assert codes_of(report) == ["ROOM_UNAVAILABLE"]
    (c,) = only(report, "ROOM_UNAVAILABLE")
    assert "Lab 1 is not available during Period 6 on Monday" in c.message


def test_room_capacity():
    ds = mini_dataset(extra_rooms=(Room(room_id="R3", name="Room 3", capacity=45),))
    entries = valid_mini_entries()
    entries[2] = entry("S1-B2-1", "Mon", 2, "R3")  # CE-B has 60 students
    report = validate(ds, entries)
    assert codes_of(report) == ["ROOM_CAPACITY"]
    assert "Room 3 seats 45 but CE-B has 60 students" in only(report, "ROOM_CAPACITY")[0].message


def test_room_type_practical_in_classroom_and_lecture_in_lab():
    entries = valid_mini_entries()
    entries[3] = entry("S2-B1-1", "Mon", 5, "R2")  # practical in a classroom
    entries[1] = entry("S1-B1-2", "Tue", 1, "L1")  # lecture in a lab
    report = validate(mini_dataset(), entries)
    assert codes_of(report) == ["ROOM_TYPE"]
    msgs = sorted(c.message for c in only(report, "ROOM_TYPE"))
    assert any("is a practical and needs a laboratory" in m for m in msgs)
    assert any("is a lecture and must be held in a classroom" in m for m in msgs)


def test_invalid_duration():
    entries = valid_mini_entries()
    entries[3] = entry("S2-B1-1", "Mon", 5, "L1", dur=1)  # practical needs 2 periods
    report = validate(mini_dataset(), entries)
    assert codes_of(report) == ["INVALID_DURATION"]
    assert "needs 2 consecutive period(s), but it is scheduled for 1" in only(report, "INVALID_DURATION")[0].message
    entries[3] = entry("S2-B1-1", "Mon", 5, "L1", dur=0)
    assert "INVALID_DURATION" in codes_of(validate(mini_dataset(), entries))


def test_outside_working_hours_day_and_period():
    ds = mini_dataset()
    entries = valid_mini_entries()
    entries[1] = entry("S1-B1-2", "Sat", 1, "R1")  # not a working day
    report = validate(ds, entries)
    assert codes_of(report) == ["OUTSIDE_WORKING_HOURS"]
    assert "Saturday is not a working day" in report.conflicts[0].message

    entries = valid_mini_entries()
    entries[1] = entry("S1-B1-2", "Tue", 9, "R1")  # after the last period
    report = validate(ds, entries)
    assert codes_of(report) == ["OUTSIDE_WORKING_HOURS"]
    assert "outside the working day (periods 1-6)" in report.conflicts[0].message

    entries = valid_mini_entries()
    entries[3] = entry("S2-B1-1", "Mon", 6, "L1")  # P6-7: runs past the last period
    assert "OUTSIDE_WORKING_HOURS" in codes_of(validate(ds, entries))


def test_blocked_period_break_and_straddling_break():
    ds = mini_dataset()  # period 4 is the break
    entries = valid_mini_entries()
    entries[1] = entry("S1-B1-2", "Tue", 4, "R1")
    report = validate(ds, entries)
    assert codes_of(report) == ["BLOCKED_PERIOD"]
    assert "Period 4" in report.conflicts[0].message and "is a break" in report.conflicts[0].message

    entries = valid_mini_entries()
    entries[3] = entry("S2-B1-1", "Mon", 3, "L1", dur=2)  # P3-4 straddles the break
    report = validate(ds, entries)
    assert codes_of(report) == ["BLOCKED_PERIOD"]
    assert "cannot run across Period 4" in report.conflicts[0].message


def test_blocked_period_non_consecutive_numbering():
    ds = mini_dataset(period_spec="1 2 3")
    ds.config.periods.pop(1)  # periods now 1 and 3 - Period 2 does not exist
    entries = [entry("S2-B1-1", "Mon", 1, "L1", dur=2)]
    report = validate(ds, entries)
    assert "BLOCKED_PERIOD" in codes_of(report)


def test_invalid_reference_variants():
    ds = mini_dataset()
    base = valid_mini_entries()
    # unknown teacher
    r = validate(ds, [base[0].model_copy(update={"teacher_id": "T99"}), *base[1:]])
    assert "INVALID_REFERENCE" in codes_of(r)
    assert "teacher 'T99'" in only(r, "INVALID_REFERENCE")[0].message
    # unknown room
    r = validate(ds, [base[0].model_copy(update={"room_id": "R99"}), *base[1:]])
    assert "room 'R99'" in only(r, "INVALID_REFERENCE")[0].message
    # session id that no requirement produces
    ghost = entry("S1-B1-9", "Tue", 2, "R1")
    r = validate(ds, [*base, ghost])
    assert "does not match any required session" in only(r, "INVALID_REFERENCE")[0].message
    # same session scheduled twice
    r = validate(ds, [*base, entry("S1-B1-1", "Tue", 2, "R1")])
    assert any("appears more than once" in c.message for c in only(r, "INVALID_REFERENCE"))
    assert not r.valid


def test_missing_session_is_a_warning_that_blocks_complete():
    entries = valid_mini_entries()[:3]  # drop the practical
    report = validate(mini_dataset(), entries)
    assert codes_of(report) == ["MISSING_SESSION"]
    (c,) = report.conflicts
    assert c.severity == "warning" and c.entry_ids == ["S2-B1-1"]
    assert report.valid and not report.complete and report.status == "valid_incomplete"
    assert (report.error_count, report.warning_count) == (0, 1)
    assert "DS Lab for CE-A" in c.message and "Prof. Iyer" in c.message
    assert "not scheduled yet" in report.summary


def test_empty_timetable_reports_every_session_missing():
    report = validate(mini_dataset(), [])
    assert len(report.conflicts) == 4 and report.counts == {"MISSING_SESSION": 4}


def test_conflicts_carry_alternative_slot_suggestions_that_are_valid():
    entries = valid_mini_entries()
    entries[2] = entry("S1-B2-1", "Mon", 1, "R2")  # teacher clash with S1-B1-1
    ds = mini_dataset()
    report = validate(ds, entries)
    (c,) = report.conflicts
    assert c.suggested_entry_id == "S1-B2-1" and c.suggestions
    for s in c.suggestions:
        moved = [e for e in entries if e.session_id != "S1-B2-1"] + [
            entry("S1-B2-1", s.day, s.start_period, s.room_id)
        ]
        assert validate(ds, moved).conflicts == [], f"suggestion {s} is not actually valid"


def test_output_order_is_deterministic_and_input_order_independent():
    ds = mini_dataset()
    entries = valid_mini_entries()
    entries[2] = entry("S1-B2-1", "Mon", 1, "R2")
    entries[3] = entry("S2-B1-1", "Mon", 1, "R1")
    a = validate(ds, entries)
    b = validate(ds, list(reversed(entries)))
    assert [c.model_dump() for c in a.conflicts] == [c.model_dump() for c in b.conflicts]
    assert a.model_dump() == validate(ds, entries).model_dump()


def test_validate_does_not_mutate_inputs():
    ds = mini_dataset()
    entries = valid_mini_entries()
    entries[2] = entry("S1-B2-1", "Mon", 1, "R2")
    ds_before, entries_before = ds.model_dump(), copy.deepcopy(entries)
    validate(ds, entries)
    assert ds.model_dump() == ds_before and entries == entries_before


def test_validator_flags_entries_that_use_availability_added_later():
    ds = add_unavailability(mini_dataset(), "T1", [("Mon", 1)])
    report = validate(ds, valid_mini_entries())
    assert "TEACHER_UNAVAILABLE" in codes_of(report)


@pytest.mark.parametrize("code", [c for c in CONFLICT_CODES if c != "MISSING_SESSION"])
def test_each_error_code_blocks_validity(code):
    """Every non-completeness code is an error that makes valid=False."""
    builders = {
        "TEACHER_OVERLAP": lambda e: e.__setitem__(2, entry("S1-B2-1", "Mon", 1, "R2")),
        "ROOM_OVERLAP": lambda e: e.__setitem__(2, entry("S1-B2-1", "Mon", 1, "R1", teacher="T2")),
        "BATCH_OVERLAP": lambda e: e.__setitem__(3, entry("S2-B1-1", "Mon", 1, "L1")),
        "TEACHER_UNAVAILABLE": None,
        "ROOM_UNAVAILABLE": None,
        "ROOM_CAPACITY": lambda e: e.__setitem__(2, entry("S1-B2-1", "Mon", 2, "R3")),
        "ROOM_TYPE": lambda e: e.__setitem__(3, entry("S2-B1-1", "Mon", 5, "R2")),
        "INVALID_DURATION": lambda e: e.__setitem__(3, entry("S2-B1-1", "Mon", 5, "L1", dur=1)),
        "OUTSIDE_WORKING_HOURS": lambda e: e.__setitem__(1, entry("S1-B1-2", "Sun", 1, "R1")),
        "BLOCKED_PERIOD": lambda e: e.__setitem__(1, entry("S1-B1-2", "Tue", 4, "R1")),
        "INVALID_REFERENCE": lambda e: e.__setitem__(0, e[0].model_copy(update={"room_id": "NOPE"})),
    }
    ds = mini_dataset(
        extra_availability=(("T1", "Tue", 1), ("L1", "Mon", 5)),
        extra_rooms=(Room(room_id="R3", name="Room 3", capacity=45),),
    )
    entries: list[Entry] = valid_mini_entries()
    if builders[code]:
        builders[code](entries)
    report = validate(ds, entries)
    assert code in codes_of(report)
    assert not report.valid and report.status == "invalid"
