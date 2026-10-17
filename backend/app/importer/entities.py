"""Row-level validation for each of the eight files.

Every ``load_*`` function reads one parsed file, reports every problem it finds
(one issue per problem, never just the first) and returns only the rows that
are fully valid.  Invalid rows are *rejected*, never repaired or dropped
silently: each one has at least one error issue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..engine.models import (
    AvailabilityRule,
    Batch,
    PeriodDef,
    Requirement,
    Room,
    Subject,
    Teacher,
)
from .fields import Row
from .reader import ParsedFile
from .report import ReportBuilder
from .schema import (
    MAX_CAPACITY,
    MAX_DURATION,
    MAX_ID_LEN,
    MAX_PERIOD_NUMBER,
    MAX_PERIOD_REF,
    MAX_SESSIONS_PER_WEEK,
    MAX_STUDENTS,
)


@dataclass
class Registry:
    """Accepted ids from files loaded so far (for reference checks).

    A file that could not be read at all (missing, wrong header, ...) is
    *unusable*: references to it are not checked, because the file-level error
    already explains the problem and checking would only add noise.
    """

    usable: set[str] = field(default_factory=set)  # file keys usable for reference checks
    teachers: dict[str, str] = field(default_factory=dict)  # id -> name
    subjects: set[str] = field(default_factory=set)
    batches: set[str] = field(default_factory=set)
    rooms: set[str] = field(default_factory=set)
    days: list[str] = field(default_factory=list)
    periods: dict[int, PeriodDef] = field(default_factory=dict)
    rejected: dict[str, dict[str, int]] = field(default_factory=dict)  # file key -> {id: row}
    rows: dict[str, dict[str, int]] = field(default_factory=dict)  # file key -> {accepted id: row}
    requirement_rows: dict[tuple[str, str, str], int] = field(default_factory=dict)

    def accept(self, key: str, ident: str, row: int) -> None:
        self.rows.setdefault(key, {})[ident] = row

    def ids(self, key: str) -> Optional[set[str]]:
        if key not in self.usable:
            return None
        return {"teachers": set(self.teachers), "subjects": self.subjects,
                "batches": self.batches, "rooms": self.rooms}[key]


def _duplicate_id(r: Row, field_name: str, value: str, seen: dict[str, tuple[int, str]], label: str) -> None:
    if value in seen:
        first_row, first_label = seen[value]
        who = f" ({first_label})" if first_label else ""
        r.error(field_name, value, "DUPLICATE_ID",
                f"{field_name} '{value}' is already used in row {first_row}{who}.",
                f"Give this {r.noun} a unique {field_name}, or delete the row if it is a repeat. The first row keeps the id.")
    else:
        seen[value] = (r.number, label)


def _note_rejected(reg: Registry, key: str, ident: Optional[str], raw_id: str, accepted: set[str] | dict, row: int) -> None:
    value = ident or raw_id
    if value and value not in accepted:
        reg.rejected.setdefault(key, {}).setdefault(value, row)


# ---------------------------------------------------------------------------
# entity files
# ---------------------------------------------------------------------------
def load_teachers(rb: ReportBuilder, parsed: ParsedFile, reg: Registry) -> list[Teacher]:
    f = parsed.spec.filename
    seen: dict[str, tuple[int, str]] = {}
    out: list[Teacher] = []
    for raw in parsed.rows:
        r = Row(rb, f, raw, "teacher")
        tid = r.ident("teacher_id")
        name = r.text("name")
        dept = r.text("department_id", required=False, max_len=MAX_ID_LEN)
        if tid is not None:
            _duplicate_id(r, "teacher_id", tid, seen, r.get("name"))
        if r.ok and tid is not None and name is not None and dept is not None:
            out.append(Teacher(teacher_id=tid, name=name, department_id=dept))
            reg.teachers[tid] = name
            reg.accept("teachers", tid, raw.number)
        else:
            _note_rejected(reg, "teachers", tid, r.get("teacher_id"), reg.teachers, raw.number)
    return out


def load_subjects(rb: ReportBuilder, parsed: ParsedFile, reg: Registry) -> list[Subject]:
    f = parsed.spec.filename
    seen: dict[str, tuple[int, str]] = {}
    out: list[Subject] = []
    for raw in parsed.rows:
        r = Row(rb, f, raw, "subject")
        sid = r.ident("subject_id")
        name = r.text("name")
        dept = r.text("department_id", required=False, max_len=MAX_ID_LEN)
        stype = r.choice("session_type", ("lecture", "practical"))
        if sid is not None:
            _duplicate_id(r, "subject_id", sid, seen, r.get("name"))
        if r.ok and sid is not None and name is not None and stype is not None and dept is not None:
            out.append(Subject(subject_id=sid, name=name, department_id=dept, session_type=stype))  # type: ignore[arg-type]
            reg.subjects.add(sid)
            reg.accept("subjects", sid, raw.number)
        else:
            _note_rejected(reg, "subjects", sid, r.get("subject_id"), reg.subjects, raw.number)
    return out


def load_batches(rb: ReportBuilder, parsed: ParsedFile, reg: Registry) -> list[Batch]:
    f = parsed.spec.filename
    seen: dict[str, tuple[int, str]] = {}
    out: list[Batch] = []
    for raw in parsed.rows:
        r = Row(rb, f, raw, "batch")
        bid = r.ident("batch_id")
        name = r.text("name")
        semester = r.text("semester", required=False, max_len=MAX_ID_LEN)
        count = r.whole("student_count", 1, MAX_STUDENTS)
        dept = r.text("department_id", required=False, max_len=MAX_ID_LEN)
        if bid is not None:
            _duplicate_id(r, "batch_id", bid, seen, r.get("name"))
        if r.ok and bid is not None and name is not None and count is not None and semester is not None and dept is not None:
            out.append(Batch(batch_id=bid, name=name, semester=semester, student_count=count, department_id=dept))
            reg.batches.add(bid)
            reg.accept("batches", bid, raw.number)
        else:
            _note_rejected(reg, "batches", bid, r.get("batch_id"), reg.batches, raw.number)
    return out


def load_rooms(rb: ReportBuilder, parsed: ParsedFile, reg: Registry) -> list[Room]:
    f = parsed.spec.filename
    seen: dict[str, tuple[int, str]] = {}
    out: list[Room] = []
    for raw in parsed.rows:
        r = Row(rb, f, raw, "room")
        rid = r.ident("room_id")
        name = r.text("name")
        capacity = r.whole("capacity", 1, MAX_CAPACITY)
        rtype = r.choice("room_type", ("classroom", "lab"))
        if rid is not None:
            _duplicate_id(r, "room_id", rid, seen, r.get("name"))
            if rid in reg.teachers:
                r.error("room_id", rid, "ID_CLASH",
                        f"room_id '{rid}' is also a teacher_id (teachers.csv). Availability rules could not tell them apart.",
                        "Give the room or the teacher a different id.")
        if r.ok and rid is not None and name is not None and capacity is not None and rtype is not None:
            out.append(Room(room_id=rid, name=name, capacity=capacity, room_type=rtype))  # type: ignore[arg-type]
            reg.rooms.add(rid)
            reg.accept("rooms", rid, raw.number)
        else:
            _note_rejected(reg, "rooms", rid, r.get("room_id"), reg.rooms, raw.number)
    return out


def load_days(rb: ReportBuilder, parsed: ParsedFile, reg: Registry) -> list[str]:
    f = parsed.spec.filename
    seen: dict[str, int] = {}
    out: list[str] = []
    for raw in parsed.rows:
        r = Row(rb, f, raw, "day")
        day = r.day("day")
        if day is not None:
            if day in seen:
                r.error("day", r.get("day"), "DUPLICATE_DAY",
                        f"{day} is already listed in row {seen[day]}.",
                        "Each working day may be listed only once; delete this row.")
            else:
                seen[day] = raw.number
        if r.ok and day is not None:
            out.append(day)
    reg.days = out
    return out


def load_periods(rb: ReportBuilder, parsed: ParsedFile, reg: Registry) -> list[PeriodDef]:
    f = parsed.spec.filename
    seen: dict[int, int] = {}
    out: list[PeriodDef] = []
    for raw in parsed.rows:
        r = Row(rb, f, raw, "period")
        number = r.whole("period", 1, MAX_PERIOD_NUMBER)
        start = r.clock("start")
        end = r.clock("end")
        is_break = r.boolean("is_break", default=False)
        if number is not None:
            if number in seen:
                r.error("period", r.get("period"), "DUPLICATE_PERIOD",
                        f"Period {number} is already defined in row {seen[number]}.",
                        "Each period number may appear once; renumber or delete this row.")
            else:
                seen[number] = raw.number
        if start is not None and end is not None and end <= start:
            r.error("end", r.get("end"), "END_NOT_AFTER_START",
                    f"The period ends at {r.get('end')}, which is not later than its start ({r.get('start')}).",
                    "End time must be later than the start time (24-hour HH:MM).")
        if r.ok and number is not None and start is not None and end is not None and is_break is not None:
            out.append(PeriodDef(period=number, start=start, end=end, is_break=is_break))
    out.sort(key=lambda p: p.period)
    reg.periods = {p.period: p for p in out}
    return out


# ---------------------------------------------------------------------------
# files that reference the others
# ---------------------------------------------------------------------------
def _check_ref(
    r: Row, reg: Registry, key: str, kind: str, file: str, field_name: str, value: str, code: str
) -> None:
    ids = reg.ids(key)
    if ids is None or value in ids:
        return
    bad_row = reg.rejected.get(key, {}).get(value)
    if bad_row is not None:
        r.error(field_name, value, code,
                f"{field_name} '{value}' refers to a {kind} in row {bad_row} of {file}, "
                "but that row has an error and was not imported.",
                f"Fix row {bad_row} of {file} first, then import again.")
    else:
        r.error(field_name, value, code,
                f"{field_name} '{value}' does not match any {kind} in {file}.",
                f"Add {value} to {file}, or correct the id here.")


def load_requirements(rb: ReportBuilder, parsed: ParsedFile, reg: Registry) -> list[Requirement]:
    f = parsed.spec.filename
    seen: dict[tuple[str, str, str], int] = {}
    out: list[Requirement] = []
    for raw in parsed.rows:
        r = Row(rb, f, raw, "requirement")
        subject = r.text("subject_id", max_len=MAX_ID_LEN)
        batch = r.text("batch_id", max_len=MAX_ID_LEN)
        teacher = r.text("teacher_id", max_len=MAX_ID_LEN)
        per_week = r.whole("sessions_per_week", 1, MAX_SESSIONS_PER_WEEK)
        duration = r.whole("duration", 1, MAX_DURATION, default=1)
        if subject:
            _check_ref(r, reg, "subjects", "subject", "subjects.csv", "subject_id", subject, "UNKNOWN_SUBJECT")
        if batch:
            _check_ref(r, reg, "batches", "batch", "batches.csv", "batch_id", batch, "UNKNOWN_BATCH")
        if teacher:
            _check_ref(r, reg, "teachers", "teacher", "teachers.csv", "teacher_id", teacher, "UNKNOWN_TEACHER")
        if subject and batch and teacher:
            key = (subject, batch, teacher)
            if key in seen:
                r.error("subject_id + batch_id + teacher_id", f"{subject} / {batch} / {teacher}",
                        "DUPLICATE_REQUIREMENT",
                        f"This subject/batch/teacher combination already appears in row {seen[key]}; "
                        "repeating it would double the weekly sessions.",
                        "Delete this row, or merge it into the first one by adding the sessions_per_week values together.")
            else:
                seen[key] = raw.number
        if r.ok and subject and batch and teacher and per_week is not None and duration is not None:
            out.append(Requirement(subject_id=subject, batch_id=batch, teacher_id=teacher,
                                   sessions_per_week=per_week, duration=duration))
            reg.requirement_rows[(subject, batch, teacher)] = raw.number
    return out


def load_availability(rb: ReportBuilder, parsed: ParsedFile, reg: Registry) -> list[AvailabilityRule]:
    """Returns only ``available=False`` rules (available is the default)."""
    f = parsed.spec.filename
    seen: dict[tuple[str, str, int], int] = {}
    out: list[AvailabilityRule] = []
    teacher_ids = reg.ids("teachers")
    room_ids = reg.ids("rooms")
    for raw in parsed.rows:
        r = Row(rb, f, raw, "availability rule")
        resource = r.text("resource_id", max_len=MAX_ID_LEN)
        day = r.day("day")
        period = r.whole("period", 1, MAX_PERIOD_REF)
        available = r.boolean("available")
        if resource:
            known = (teacher_ids is not None and resource in teacher_ids) or (
                room_ids is not None and resource in room_ids
            )
            if not known and teacher_ids is not None and room_ids is not None:
                bad_row = reg.rejected.get("teachers", {}).get(resource) or reg.rejected.get("rooms", {}).get(resource)
                if bad_row is not None:
                    r.error("resource_id", resource, "UNKNOWN_RESOURCE",
                            f"resource_id '{resource}' refers to a record in row {bad_row} that has an error and was not imported.",
                            "Fix that row first, then import again.")
                else:
                    r.error("resource_id", resource, "UNKNOWN_RESOURCE",
                            f"resource_id '{resource}' is neither a teacher_id (teachers.csv) nor a room_id (rooms.csv).",
                            "Use an existing teacher_id or room_id, or add the missing teacher or room to its file.")
        if day is not None and "days" in reg.usable and day not in reg.days:
            r.error("day", r.get("day"), "DAY_NOT_IN_DAYS_FILE",
                    f"{day} is not one of the working days in days.csv ({', '.join(reg.days)}).",
                    f"Add {day} to days.csv, or delete this row.")
            day = None
        if period is not None and "periods" in reg.usable:
            pdef = reg.periods.get(period)
            if pdef is None:
                r.error("period", r.get("period"), "UNKNOWN_PERIOD",
                        f"Period {period} is not defined in periods.csv.",
                        "Use a period number that exists in periods.csv, or add the period there.")
                period = None
            elif pdef.is_break and r.ok:
                r.warn("period", r.get("period"), "AVAILABILITY_ON_BREAK",
                       f"Period {period} is a break, so nobody can be scheduled then anyway; this rule has no effect.",
                       "Delete the row, or check that you meant a different period.")
        if not r.ok or resource is None or day is None or period is None or available is None:
            continue
        key = (resource, day, period)
        if key in seen:
            r.warn(None, None, "DUPLICATE_AVAILABILITY",
                   f"{resource} / {day} / Period {period} is already listed in row {seen[key]}; this repeat was ignored.",
                   "Delete the repeated row.")
            continue
        seen[key] = raw.number
        if available:
            r.warn("available", r.get("available"), "REDUNDANT_AVAILABILITY",
                   "This row says the resource is available, which is already the default, so it was ignored.",
                   "You only need to list the slots where someone or something is NOT available (0/no/false).")
            continue
        out.append(AvailabilityRule(resource_id=resource, day=day, period=period, available=False))
    return out
