"""The CSV file set SmartSlot imports (see sample_data/README.md)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileSpec:
    key: str  # short name used in counts, e.g. "teachers"
    filename: str  # "teachers.csv"
    required: bool
    columns: tuple[str, ...]  # every known column, in template order
    required_columns: tuple[str, ...]
    description: str

    @property
    def header_line(self) -> str:
        return ",".join(self.columns)


# Order matters: it is the order of the report and of validation (referenced
# files first would also work, but README order is what users know).
FILE_SPECS: tuple[FileSpec, ...] = (
    FileSpec(
        "teachers", "teachers.csv", True,
        ("teacher_id", "name", "department_id"),
        ("teacher_id", "name"),
        "Teachers",
    ),
    FileSpec(
        "subjects", "subjects.csv", True,
        ("subject_id", "name", "department_id", "session_type"),
        ("subject_id", "name", "session_type"),
        "Subjects",
    ),
    FileSpec(
        "batches", "batches.csv", True,
        ("batch_id", "name", "semester", "student_count", "department_id"),
        ("batch_id", "name", "student_count"),
        "Student batches",
    ),
    FileSpec(
        "rooms", "rooms.csv", True,
        ("room_id", "name", "capacity", "room_type"),
        ("room_id", "name", "capacity", "room_type"),
        "Rooms",
    ),
    FileSpec(
        "requirements", "requirements.csv", True,
        ("subject_id", "batch_id", "teacher_id", "sessions_per_week", "duration"),
        ("subject_id", "batch_id", "teacher_id", "sessions_per_week"),
        "Weekly requirements",
    ),
    FileSpec(
        "days", "days.csv", True,
        ("day",),
        ("day",),
        "Working days",
    ),
    FileSpec(
        "periods", "periods.csv", True,
        ("period", "start", "end", "is_break"),
        ("period", "start", "end"),
        "Periods and breaks",
    ),
    FileSpec(
        "availability", "availability.csv", False,
        ("resource_id", "day", "period", "available"),
        ("resource_id", "day", "period", "available"),
        "Availability exceptions",
    ),
)

SPEC_BY_KEY: dict[str, FileSpec] = {s.key: s for s in FILE_SPECS}
SPEC_BY_FILENAME: dict[str, FileSpec] = {s.filename: s for s in FILE_SPECS}
FILE_ORDER: dict[str, int] = {s.filename: i for i, s in enumerate(FILE_SPECS)}

# Sensible upper bounds (a typo such as 600 sessions per week is an error).
MAX_NAME_LEN = 120
MAX_ID_LEN = 40
MAX_STUDENTS = 10_000
MAX_CAPACITY = 10_000
MAX_SESSIONS_PER_WEEK = 60
MAX_DURATION = 12
MAX_PERIOD_NUMBER = 99
MAX_PERIOD_REF = 999
