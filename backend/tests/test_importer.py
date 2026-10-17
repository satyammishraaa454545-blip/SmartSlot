"""CSV importer: row-level validation, file-level problems, secure file handling."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app import settings
from app.importer import IncomingFile, import_files, sample_uploads, template_csv, templates_zip

SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample_data"

GOOD = {
    "teachers.csv": "teacher_id,name,department_id\nT1,Dr. Sharma,CE\nT2,Prof. Iyer,CE\n",
    "subjects.csv": "subject_id,name,department_id,session_type\nS1,Data Structures,CE,lecture\nS2,DS Lab,CE,practical\n",
    "batches.csv": "batch_id,name,semester,student_count,department_id\nB1,CE-A,3,40,CE\n",
    "rooms.csv": "room_id,name,capacity,room_type\nR1,Room 1,60,classroom\nL1,Lab 1,60,lab\n",
    "requirements.csv": "subject_id,batch_id,teacher_id,sessions_per_week,duration\nS1,B1,T1,3,1\nS2,B1,T2,1,2\n",
    "days.csv": "day\nMon\nTue\n",
    "periods.csv": "period,start,end,is_break\n1,09:00,09:50,0\n2,09:50,10:40,0\n3,10:40,11:30,1\n4,11:30,12:20,0\n",
    "availability.csv": "resource_id,day,period,available\nT1,Mon,1,0\n",
}


def files(overrides: dict[str, str | bytes | None] | None = None) -> list[IncomingFile]:
    data: dict[str, str | bytes | None] = dict(GOOD)
    data.update(overrides or {})
    out = []
    for name, content in data.items():
        if content is None:
            continue
        raw = content if isinstance(content, bytes) else content.encode("utf-8")
        out.append(IncomingFile(filename=name, data=raw, field="files"))
    return out


def run(overrides: dict[str, str | bytes | None] | None = None, semester: str = "3"):
    return import_files(files(overrides), name="t", semester=semester)


def codes(result, file: str | None = None, severity: str = "error") -> list[str]:
    return [i.code for i in result.report.issues if i.severity == severity and (file is None or i.file == file)]


# ---------------------------------------------------------------------------
# the three bundled samples
# ---------------------------------------------------------------------------
def test_feasible_and_infeasible_samples_import_clean() -> None:
    for kind, sessions in (("feasible", 60), ("infeasible", 66)):
        res = import_files(sample_uploads(kind) or [], name=kind, semester="3")
        assert res.report.status == "ok", [i.message for i in res.report.issues]
        assert res.report.error_count == 0
        assert res.report.total_sessions == sessions
        assert res.report.counts["teachers"] == 6 and res.report.counts["rooms"] == 4
        assert all(f.present for f in res.report.files)


# (file, row, field, value, code) - the 35 documented errors of sample_data/invalid/EXPECTED_ERRORS.md
EXPECTED_35 = [
    ("teachers.csv", 6, "teacher_id", "T03", "DUPLICATE_ID"),
    ("teachers.csv", 7, "name", "", "MISSING_FIELD"),
    ("teachers.csv", 8, "teacher_id", "", "MISSING_FIELD"),
    ("subjects.csv", 6, "session_type", "seminar", "INVALID_CHOICE"),
    ("subjects.csv", 7, "subject_id", "CS202", "DUPLICATE_ID"),
    ("batches.csv", 4, "student_count", "abc", "NOT_A_NUMBER"),
    ("batches.csv", 5, "student_count", "-5", "OUT_OF_RANGE"),
    ("batches.csv", 6, "batch_id", "CE-A", "DUPLICATE_ID"),
    ("batches.csv", 7, "name", "", "MISSING_FIELD"),
    ("rooms.csv", 5, "capacity", "abc", "NOT_A_NUMBER"),
    ("rooms.csv", 6, "room_type", "auditorium", "INVALID_CHOICE"),
    ("rooms.csv", 7, "room_id", "R101", "DUPLICATE_ID"),
    ("rooms.csv", 8, "capacity", "0", "OUT_OF_RANGE"),
    ("requirements.csv", 6, "teacher_id", "T99", "UNKNOWN_TEACHER"),
    ("requirements.csv", 7, "subject_id", "XX999", "UNKNOWN_SUBJECT"),
    ("requirements.csv", 8, "batch_id", "CE-Z", "UNKNOWN_BATCH"),
    ("requirements.csv", 9, "sessions_per_week", "0", "OUT_OF_RANGE"),
    ("requirements.csv", 10, "sessions_per_week", "four", "NOT_A_NUMBER"),
    ("requirements.csv", 11, "duration", "two", "NOT_A_NUMBER"),
    ("requirements.csv", 12, "subject_id", "", "MISSING_FIELD"),
    ("requirements.csv", 13, "duration", "0", "OUT_OF_RANGE"),
    ("requirements.csv", 14, "subject_id + batch_id + teacher_id", "CS201 / CE-A / T01", "DUPLICATE_REQUIREMENT"),
    ("availability.csv", 5, "resource_id", "T77", "UNKNOWN_RESOURCE"),
    ("availability.csv", 6, "day", "Funday", "INVALID_DAY"),
    ("availability.csv", 7, "day", "Sat", "DAY_NOT_IN_DAYS_FILE"),
    ("availability.csv", 8, "period", "15", "UNKNOWN_PERIOD"),
    ("availability.csv", 9, "period", "abc", "NOT_A_NUMBER"),
    ("availability.csv", 10, "available", "maybe", "INVALID_CHOICE"),
    ("days.csv", 7, "day", "Tue", "DUPLICATE_DAY"),
    ("days.csv", 8, "day", "Holiday", "INVALID_DAY"),
    ("periods.csv", 9, "period", "3", "DUPLICATE_PERIOD"),
    ("periods.csv", 10, "start", "9am", "INVALID_TIME"),
    ("periods.csv", 11, "end", "16:40", "END_NOT_AFTER_START"),
    ("periods.csv", 12, "is_break", "maybe", "INVALID_CHOICE"),
    ("periods.csv", 13, "period", "x", "NOT_A_NUMBER"),
]


def test_invalid_sample_reports_exactly_the_35_documented_errors() -> None:
    res = import_files(sample_uploads("invalid") or [], name="bad", semester="3")
    rep = res.report
    assert rep.status == "has_errors"
    assert len(EXPECTED_35) == 35
    found = {
        (i.file, i.row, i.field, i.value, i.code): i for i in rep.issues if i.severity == "error"
    }
    assert rep.error_count == 35 == len(found)
    for expected in EXPECTED_35:
        assert expected in found, f"missing expected error {expected}"
        issue = found[expected]
        assert issue.message and issue.how_to_fix, "every error explains itself and how to fix it"


def test_invalid_sample_keeps_valid_rows_and_rejects_bad_ones() -> None:
    res = import_files(sample_uploads("invalid") or [], name="bad", semester="3")
    ids = {t.teacher_id for t in res.dataset.teachers}
    assert ids == {"T01", "T02", "T03", "T04"}  # rows 6, 7, 8 rejected, first T03 kept
    assert [t.name for t in res.dataset.teachers if t.teacher_id == "T03"] == ["Dr. Mehta"]
    summary = {f.file: f for f in res.report.files}["teachers.csv"]
    assert (summary.rows, summary.accepted, summary.rejected) == (7, 4, 3)
    assert {r.room_id for r in res.dataset.rooms} == {"R101", "R102", "LAB1"}
    assert res.dataset.config.days == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    assert {p.period for p in res.dataset.config.periods} == {1, 2, 3, 4, 5, 6, 7}


def test_every_issue_has_the_documented_fields_and_sorted_rows() -> None:
    res = import_files(sample_uploads("invalid") or [], name="bad", semester="3")
    for i in res.report.issues:
        assert i.severity in ("error", "warning") and i.code
    teachers = [i.row for i in res.report.issues if i.file == "teachers.csv" and i.severity == "error"]
    assert teachers == sorted(teachers)


# ---------------------------------------------------------------------------
# file-level problems
# ---------------------------------------------------------------------------
def test_good_data_is_clean() -> None:
    res = run()
    assert res.report.status == "ok", [i.message for i in res.report.issues]
    assert res.report.total_sessions == 4
    assert res.dataset.semester == "3"


def test_missing_required_file_is_an_error_and_cascade_is_suppressed() -> None:
    res = run({"teachers.csv": None})
    assert "MISSING_FILE" in codes(res, "teachers.csv")
    # requirements referencing teachers are NOT flagged one by one
    assert "UNKNOWN_TEACHER" not in codes(res)
    assert res.report.status == "has_errors"


def test_availability_file_is_optional() -> None:
    res = run({"availability.csv": None})
    assert res.report.status == "ok"
    assert res.dataset.availability == []


def test_empty_file_and_header_only_file() -> None:
    assert "EMPTY_FILE" in codes(run({"rooms.csv": ""}), "rooms.csv")
    assert "EMPTY_FILE" in codes(run({"rooms.csv": "   \r\n\r\n"}), "rooms.csv")
    header_only = run({"rooms.csv": "room_id,name,capacity,room_type\n"})
    assert "EMPTY_FILE" in codes(header_only, "rooms.csv")
    assert run({"availability.csv": ""}).report.status == "ok"  # optional file may be blank


def test_wrong_header_and_missing_column() -> None:
    wrong = run({"teachers.csv": "id,full_name\nT1,Dr. A\n"})
    assert "WRONG_HEADER" in codes(wrong, "teachers.csv")
    missing = run({"rooms.csv": "room_id,name,room_type\nR1,Room 1,classroom\n"})
    issue = next(i for i in missing.report.issues if i.code == "MISSING_COLUMN")
    assert (issue.file, issue.field, issue.row) == ("rooms.csv", "capacity", 1)


def test_header_is_case_and_order_insensitive_and_unknown_columns_warn() -> None:
    res = run({"teachers.csv": "Name,Teacher ID,Extra\nDr. A,T1,x\nDr. B,T2,y\n"})
    assert res.report.status == "ok"
    assert [t.teacher_id for t in res.dataset.teachers] == ["T1", "T2"]
    assert "UNKNOWN_COLUMN" in codes(res, "teachers.csv", "warning")


def test_bad_encoding_is_reported_not_guessed() -> None:
    latin1 = "teacher_id,name\nT1,Dr. Müller\n".encode("cp1252")
    res = run({"teachers.csv": latin1})
    assert "BAD_ENCODING" in codes(res, "teachers.csv")
    utf16 = "teacher_id,name\nT1,Dr. A\n".encode("utf-16")
    assert "BAD_ENCODING" in codes(run({"teachers.csv": utf16}), "teachers.csv")


def test_utf8_bom_and_non_ascii_names_are_fine() -> None:
    res = run({"teachers.csv": "﻿teacher_id,name\nT1,Dr. Müller\nT2,प्रो. शर्मा\n"})
    assert res.report.status == "ok"
    assert [t.name for t in res.dataset.teachers] == ["Dr. Müller", "प्रो. शर्मा"]


def test_non_csv_content_is_rejected() -> None:
    xlsx = b"PK\x03\x04" + b"\x00" * 50
    assert "NOT_CSV" in codes(run({"teachers.csv": xlsx}), "teachers.csv")
    assert "NOT_CSV" in codes(run({"teachers.csv": b"%PDF-1.4 whatever"}), "teachers.csv")
    assert "NOT_CSV" in codes(run({"teachers.csv": b"teacher_id,name\nT1,\x00\x00A\n"}), "teachers.csv")
    res = import_files([*files({"teachers.csv": None}), IncomingFile("teachers.xlsx", b"PK\x03\x04junk")], "t", "3")
    assert any(i.code == "NOT_CSV" and i.file == "teachers.xlsx" for i in res.report.issues)
    assert "MISSING_FILE" in codes(res, "teachers.csv")


def test_unknown_csv_is_ignored_with_a_warning() -> None:
    res = import_files([*files(), IncomingFile("notes.csv", b"a,b\n1,2\n")], "t", "3")
    assert res.report.status == "ok"
    assert "UNKNOWN_FILE" in codes(res, "notes.csv", "warning")


def test_oversize_file_is_rejected_without_reading_it() -> None:
    big = IncomingFile("teachers.csv", None, field="files", too_large=True)
    res = import_files([big, *[f for f in files() if f.filename != "teachers.csv"]], "t", "3")
    assert "FILE_TOO_LARGE" in codes(res, "teachers.csv")
    assert "MISSING_FILE" not in codes(res, "teachers.csv")


def test_semicolon_separated_file_gets_a_helpful_error() -> None:
    res = run({"teachers.csv": "teacher_id;name\nT1;Dr. A\n"})
    assert "WRONG_DELIMITER" in codes(res, "teachers.csv")


def test_unclosed_quote_is_a_clear_error() -> None:
    res = run({"teachers.csv": 'teacher_id,name\nT1,"Dr. A\nT2,B"x\n'})
    assert "MALFORMED_CSV" in codes(res, "teachers.csv")


def test_duplicate_upload_of_same_file() -> None:
    res = import_files([*files(), IncomingFile("teachers.csv", GOOD["teachers.csv"].encode())], "t", "3")
    assert "DUPLICATE_FILE" in codes(res, "teachers.csv")


def test_file_names_with_paths_are_not_trusted() -> None:
    # a client sending a path-like name only gets its base name compared with the known names
    uploads = [IncomingFile(f"../../etc/{f.filename}", f.data) for f in files()]
    res = import_files(uploads, "t", "3")
    assert res.report.status == "ok"
    backslashes = [IncomingFile("..\\..\\teachers.csv", GOOD["teachers.csv"].encode())]
    res = import_files([*backslashes, *[f for f in files() if f.filename != "teachers.csv"]], "t", "3")
    assert res.report.status == "ok" and res.report.counts["teachers"] == 2


# ---------------------------------------------------------------------------
# zip handling
# ---------------------------------------------------------------------------
def make_zip(members: dict[str, bytes | str], *, compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_zip_with_the_csvs_imports_like_loose_files() -> None:
    data = make_zip(dict(GOOD))
    res = import_files([IncomingFile("timetable.zip", data)], "t", "3")
    assert res.report.status == "ok", [i.message for i in res.report.issues]
    assert res.report.counts["teachers"] == 2


def test_zip_with_a_top_level_folder_and_os_junk() -> None:
    members = {f"export/{k}": v for k, v in GOOD.items()}
    members["__MACOSX/export/._teachers.csv"] = "junk"
    members["export/.DS_Store"] = "junk"
    res = import_files([IncomingFile("x.zip", make_zip(members))], "t", "3")
    assert res.report.status == "ok", [i.message for i in res.report.issues]
    assert res.report.warning_count == 0


def test_zip_slip_paths_are_skipped_and_never_written() -> None:
    members = dict(GOOD)
    members["../../evil.csv"] = "a,b\n1,2\n"
    members["/abs/evil.csv"] = "a,b\n1,2\n"
    res = import_files([IncomingFile("x.zip", make_zip(members))], "t", "3")
    assert res.report.status == "ok"
    unsafe = [i for i in res.report.issues if i.code == "UNSAFE_ZIP_PATH"]
    assert len(unsafe) == 2 and all(i.severity == "warning" for i in unsafe)
    assert not Path("/abs/evil.csv").exists() and not (Path.cwd().parents[1] / "evil.csv").exists()


def test_zip_member_count_and_size_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    many = {f"f{i}.csv": "a\n" for i in range(settings.MAX_ZIP_MEMBERS + 1)}
    res = import_files([IncomingFile("x.zip", make_zip(many))], "t", "3")
    assert "ZIP_TOO_MANY_FILES" in codes(res, "x.zip")

    monkeypatch.setattr(settings, "MAX_FILE_BYTES", 1000)
    big = dict(GOOD)
    big["teachers.csv"] = "teacher_id,name\n" + "T1,Aaaaaaaaaaaaaaaaaaaaaaaa\n" * 200
    res = import_files([IncomingFile("x.zip", make_zip(big))], "t", "3")
    assert "FILE_TOO_LARGE" in codes(res, "teachers.csv")


def test_zip_bomb_is_stopped_by_the_total_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MAX_ZIP_TOTAL_BYTES", 5000)
    bomb = {"teachers.csv": "teacher_id,name\n" + "T,A\n" * 4000, "subjects.csv": "x\n" * 3000}
    res = import_files([IncomingFile("x.zip", make_zip(bomb))], "t", "3")
    assert "ZIP_TOO_LARGE" in codes(res)


def test_corrupt_zip_is_reported() -> None:
    res = import_files([IncomingFile("x.zip", b"PK\x03\x04 this is not really a zip")], "t", "3")
    assert "BAD_ZIP" in codes(res, "x.zip")


# ---------------------------------------------------------------------------
# row-level rules beyond the 35 samples
# ---------------------------------------------------------------------------
def test_one_row_with_several_problems_reports_all_of_them() -> None:
    res = run({"rooms.csv": "room_id,name,capacity,room_type\nR1,,abc,spaceship\n"})
    row_issues = [(i.field, i.code) for i in res.report.issues if i.file == "rooms.csv" and i.severity == "error"]
    assert row_issues == [("name", "MISSING_FIELD"), ("capacity", "NOT_A_NUMBER"), ("room_type", "INVALID_CHOICE")]


def test_reference_to_a_rejected_row_explains_the_cascade() -> None:
    res = run({"teachers.csv": "teacher_id,name\nT1,Dr. A\nT2,\n"})  # T2 has no name -> rejected
    issue = next(i for i in res.report.issues if i.code == "UNKNOWN_TEACHER")
    assert "row 3" in issue.message and "not imported" in issue.message


def test_row_with_too_many_cells_is_rejected_with_a_quoting_hint() -> None:
    res = run({"teachers.csv": "teacher_id,name\nT1,Smith, J.\nT2,Dr. B\n"})
    issue = next(i for i in res.report.issues if i.code == "TOO_MANY_CELLS")
    assert issue.row == 2 and "double quotes" in issue.how_to_fix
    assert [t.teacher_id for t in res.dataset.teachers] == ["T2"]


def test_quoted_commas_blank_lines_and_spaces() -> None:
    res = run({"teachers.csv": 'teacher_id,name\n\n  T1  ,"Smith, J."\n\nT2 ,  Dr.   B \n'})
    assert res.report.status == "ok"
    assert [(t.teacher_id, t.name) for t in res.dataset.teachers] == [("T1", "Smith, J."), ("T2", "Dr. B")]


def test_blank_lines_still_count_towards_spreadsheet_row_numbers() -> None:
    res = run({"rooms.csv": "room_id,name,capacity,room_type\n\nR1,Room 1,abc,classroom\n"})
    issue = next(i for i in res.report.issues if i.code == "NOT_A_NUMBER")
    assert issue.row == 3


def test_day_aliases_and_bool_and_time_forms_are_accepted() -> None:
    res = run({
        "days.csv": "day\nMonday\ntue\n",
        "periods.csv": "period,start,end,is_break\n1,9:00,9:50,no\n2,9:50,10:40,FALSE\n3,10:40,11:30,Yes\n4,11:30,12:20,\n",
    })
    assert res.report.status == "ok", [i.message for i in res.report.issues]
    assert res.dataset.config.days == ["Mon", "Tue"]
    assert [(p.start, p.is_break) for p in res.dataset.config.periods] == [
        ("09:00", False), ("09:50", False), ("10:40", True), ("11:30", False)]


def test_ids_with_unsafe_characters_are_rejected() -> None:
    res = run({"teachers.csv": "teacher_id,name\nT/1,Dr. A\nT2,Dr. B\n"})
    assert "INVALID_ID" in codes(res, "teachers.csv")


def test_teacher_and_room_ids_must_not_collide() -> None:
    res = run({"rooms.csv": "room_id,name,capacity,room_type\nT1,Room T1,60,classroom\n"})
    assert "ID_CLASH" in codes(res, "rooms.csv")


def test_numbers_have_sane_upper_bounds() -> None:
    res = run({"batches.csv": "batch_id,name,student_count\nB1,CE-A,999999\n"})
    assert "OUT_OF_RANGE" in codes(res, "batches.csv")
    res = run({"requirements.csv": "subject_id,batch_id,teacher_id,sessions_per_week\nS1,B1,T1,500\n"})
    assert "OUT_OF_RANGE" in codes(res, "requirements.csv")


def test_duration_column_is_optional_and_defaults_to_one() -> None:
    res = run({"requirements.csv": "subject_id,batch_id,teacher_id,sessions_per_week\nS1,B1,T1,3\n"})
    assert res.report.status == "ok"
    assert res.dataset.requirements[0].duration == 1


def test_no_teaching_period_is_an_error() -> None:
    res = run({"periods.csv": "period,start,end,is_break\n1,09:00,09:50,1\n"})
    assert "NO_TEACHING_PERIODS" in codes(res, "periods.csv")


# ---------------------------------------------------------------------------
# warnings (importable, but worth knowing)
# ---------------------------------------------------------------------------
def test_unused_records_and_semester_mismatch_are_warnings_not_errors() -> None:
    res = run({
        "batches.csv": "batch_id,name,semester,student_count\nB1,CE-A,3,40\nB2,CE-B,5,40\n",
        "teachers.csv": GOOD["teachers.csv"] + "T3,Dr. Idle,CE\n",
        "subjects.csv": GOOD["subjects.csv"] + "S3,Unused,CE,lecture\n",
    })
    assert res.report.status == "ok"
    warn = codes(res, severity="warning")
    for code in ("BATCH_WITHOUT_REQUIREMENTS", "TEACHER_WITHOUT_REQUIREMENTS", "SUBJECT_WITHOUT_REQUIREMENTS",
                 "SEMESTER_MISMATCH"):
        assert code in warn, code
    batch_warning = next(i for i in res.report.issues if i.code == "BATCH_WITHOUT_REQUIREMENTS")
    assert (batch_warning.file, batch_warning.row, batch_warning.field) == ("batches.csv", 3, "batch_id")


def test_availability_on_a_break_and_redundant_rows_are_warnings() -> None:
    res = run({"availability.csv": "resource_id,day,period,available\nT1,Mon,3,0\nT1,Mon,1,1\nT2,Tue,1,0\nT2,Tue,1,0\n"})
    assert res.report.status == "ok"
    warn = codes(res, "availability.csv", "warning")
    assert {"AVAILABILITY_ON_BREAK", "REDUNDANT_AVAILABILITY", "DUPLICATE_AVAILABILITY"} <= set(warn)
    stored = {(a.resource_id, a.day, a.period) for a in res.dataset.availability}
    assert stored == {("T1", "Mon", 3), ("T2", "Tue", 1)}  # the available=1 row and the repeat are not stored


def test_teacher_overload_is_not_an_import_error() -> None:
    # 30 sessions/week for one teacher cannot fit in 2 days x 3 periods - that is the scheduler's job
    res = run({"requirements.csv": "subject_id,batch_id,teacher_id,sessions_per_week,duration\nS1,B1,T1,30,1\n"})
    assert res.report.status == "ok"


def test_duration_longer_than_any_teaching_stretch_warns() -> None:
    res = run({"requirements.csv": "subject_id,batch_id,teacher_id,sessions_per_week,duration\nS2,B1,T2,1,5\n"})
    assert res.report.status == "ok"
    assert "DURATION_TOO_LONG" in codes(res, "requirements.csv", "warning")


def test_issue_storage_is_capped_but_counts_stay_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MAX_ISSUES_PER_FILE", 5)
    rows = "".join(f"R{i},Room,abc,classroom\n" for i in range(30))
    res = run({"rooms.csv": "room_id,name,capacity,room_type\n" + rows})
    assert res.report.error_count == 30
    assert len([i for i in res.report.issues if i.file == "rooms.csv"]) == 5
    assert res.report.truncated is True


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------
def test_templates_match_the_documented_headers_and_zip_has_all_eight() -> None:
    for path in sorted((SAMPLE_ROOT / "templates").glob("*.csv")):
        assert template_csv(path.stem) == path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n") or \
            template_csv(path.stem).decode().strip() == path.read_text(encoding="utf-8").strip()
    assert template_csv("nope") is None
    with zipfile.ZipFile(io.BytesIO(templates_zip())) as zf:
        assert sorted(zf.namelist()) == sorted(f"{p.stem}.csv" for p in (SAMPLE_ROOT / "templates").glob("*.csv"))


def test_blank_templates_round_trip_as_empty_file_errors_not_crashes() -> None:
    uploads = [IncomingFile(f"{p.stem}.csv", template_csv(p.stem)) for p in (SAMPLE_ROOT / "templates").glob("*.csv")]
    res = import_files(uploads, "blank", "")
    assert res.report.status == "has_errors"
    assert "EMPTY_FILE" in codes(res, "teachers.csv")
    assert not any(i.file == "availability.csv" for i in res.report.issues if i.severity == "error")


def test_absurdly_long_numbers_and_cells_cannot_break_the_importer() -> None:
    res = run({"batches.csv": "batch_id,name,student_count\nB1,CE-A," + "9" * 5000 + "\nB2,CE-B,-" + "9" * 400 + "\n"})
    assert codes(res, "batches.csv").count("OUT_OF_RANGE") == 2
    huge = "x" * 100_000
    res = run({"subjects.csv": f"subject_id,name,session_type\nS1,A,{huge}\n"})
    issue = next(i for i in res.report.issues if i.code == "INVALID_CHOICE")
    assert len(issue.value or "") <= 80 and len(issue.message) <= 400
