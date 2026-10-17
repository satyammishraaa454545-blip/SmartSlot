"""Domain models for the SmartSlot scheduling engine.

Pure data definitions (Pydantic v2).  Nothing in this module knows about
FastAPI, the database, or the CSV importer, so the engine can be tested and
reused on its own.

Conventions (see docs/ARCHITECTURE.md):
  * days are short names such as ``Mon``; periods are 1-based integers;
  * a break is a period with ``is_break=True`` and can never hold a session;
  * ``Entry.entry_id`` is the same string as ``Entry.session_id``.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

SessionType = Literal["lecture", "practical"]
RoomType = Literal["classroom", "lab"]
Severity = Literal["error", "warning"]
ResultStatus = Literal["complete", "partial", "failed"]

# Stable validator conflict codes (docs/ARCHITECTURE.md).
CONFLICT_CODES: tuple[str, ...] = (
    "TEACHER_OVERLAP",
    "ROOM_OVERLAP",
    "BATCH_OVERLAP",
    "TEACHER_UNAVAILABLE",
    "ROOM_UNAVAILABLE",
    "ROOM_CAPACITY",
    "ROOM_TYPE",
    "INVALID_DURATION",
    "OUTSIDE_WORKING_HOURS",
    "BLOCKED_PERIOD",
    "INVALID_REFERENCE",
    "MISSING_SESSION",
)


# --------------------------------------------------------------------------
# Input data
# --------------------------------------------------------------------------
class Teacher(BaseModel):
    teacher_id: str
    name: str
    department_id: str = ""


class Subject(BaseModel):
    subject_id: str
    name: str
    department_id: str = ""
    session_type: SessionType = "lecture"


class Batch(BaseModel):
    batch_id: str
    name: str
    semester: str = ""
    student_count: int = Field(ge=1)
    department_id: str = ""


class Room(BaseModel):
    room_id: str
    name: str
    capacity: int = Field(ge=1)
    room_type: RoomType = "classroom"


class AvailabilityRule(BaseModel):
    """One row of availability.csv.  Only ``available=False`` rows have an
    effect; the default for every (resource, day, period) is *available*."""

    resource_id: str  # a teacher_id or a room_id
    day: str
    period: int
    available: bool


class Requirement(BaseModel):
    subject_id: str
    batch_id: str
    teacher_id: str
    sessions_per_week: int = Field(ge=1)
    duration: int = Field(default=1, ge=1)  # consecutive periods per session


class PeriodDef(BaseModel):
    period: int = Field(ge=1)
    start: str  # "HH:MM"
    end: str  # "HH:MM"
    is_break: bool = False


class Config(BaseModel):
    days: list[str] = Field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri"])
    periods: list[PeriodDef] = Field(default_factory=list)


class Dataset(BaseModel):
    """Everything the engine needs for one semester."""

    name: str = ""
    semester: str = ""
    teachers: list[Teacher] = Field(default_factory=list)
    subjects: list[Subject] = Field(default_factory=list)
    batches: list[Batch] = Field(default_factory=list)
    rooms: list[Room] = Field(default_factory=list)
    availability: list[AvailabilityRule] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    config: Config = Field(default_factory=Config)


# --------------------------------------------------------------------------
# Sessions and timetable entries
# --------------------------------------------------------------------------
class Session(BaseModel):
    """One weekly occurrence a requirement expands into (e.g. CS201-CE-A-2)."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    subject_id: str
    batch_id: str
    teacher_id: str
    duration: int
    session_type: SessionType = "lecture"
    index: int  # 1-based position inside its (subject, batch) pair
    of: int  # sessions_per_week of the requirement it came from
    requirement_index: int  # position of the requirement in dataset.requirements


class Entry(BaseModel):
    """A session placed on the timetable."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    day: str
    start_period: int
    duration: int
    teacher_id: str
    room_id: str
    subject_id: str
    batch_id: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entry_id(self) -> str:
        """Same string as ``session_id`` (a session is placed at most once)."""
        return self.session_id

    @property
    def periods(self) -> range:
        return range(self.start_period, self.start_period + max(self.duration, 0))


class Suggestion(BaseModel):
    """An alternative placement that passes validation."""

    day: str
    start_period: int
    room_id: str
    teacher_id: Optional[str] = None


# --------------------------------------------------------------------------
# Validation output
# --------------------------------------------------------------------------
class Involved(BaseModel):
    teacher_id: Optional[str] = None
    room_id: Optional[str] = None
    batch_id: Optional[str] = None
    subject_id: Optional[str] = None


class Conflict(BaseModel):
    code: str
    severity: Severity
    message: str
    day: Optional[str] = None
    period: Optional[int] = None
    entry_ids: list[str] = Field(default_factory=list)
    involved: Involved = Field(default_factory=Involved)
    suggestions: list[Suggestion] = Field(default_factory=list)
    # The entry that ``suggestions`` are alternatives for (the one to move).
    suggested_entry_id: Optional[str] = None


class ValidationReport(BaseModel):
    valid: bool  # no error-severity conflicts (safe to publish)
    complete: bool  # valid AND every required session is scheduled
    status: Literal["valid_complete", "valid_incomplete", "invalid"]
    error_count: int
    warning_count: int
    counts: dict[str, int] = Field(default_factory=dict)  # per conflict code
    summary: str = ""
    conflicts: list[Conflict] = Field(default_factory=list)

    def codes(self) -> list[str]:
        return sorted({c.code for c in self.conflicts})


class MoveResult(BaseModel):
    """Outcome of a dry-run edit (validate_move / validate_place)."""

    valid: bool
    entry: Optional[Entry] = None  # the proposed entry (None if it could not be built)
    conflicts: list[Conflict] = Field(default_factory=list)
    affected_entries: list[Entry] = Field(default_factory=list)  # classes it clashes with
    suggestions: list[Suggestion] = Field(default_factory=list)
    message: str = ""


# --------------------------------------------------------------------------
# Generation output
# --------------------------------------------------------------------------
class UnscheduledItem(BaseModel):
    session: Session
    reasons: list[str]
    reason_codes: list[str] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)  # how a coordinator could fix it


class SearchStats(BaseModel):
    nodes: int = 0
    elapsed_ms: int = 0
    hit_limit: bool = False  # stopped by max_nodes / time_limit_s
    exhausted: bool = False  # search space fully explored without a complete solution
    max_nodes: int = 0
    time_limit_s: float = 0.0
    total_sessions: int = 0
    scheduled_count: int = 0


class ScheduleResult(BaseModel):
    status: ResultStatus
    message: str
    scheduled: list[Entry] = Field(default_factory=list)
    unscheduled: list[UnscheduledItem] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)  # resource-level explanations
    stats: SearchStats = Field(default_factory=SearchStats)
    validation: ValidationReport


# --------------------------------------------------------------------------
# Analytics output
# --------------------------------------------------------------------------
class TeacherLoad(BaseModel):
    teacher_id: str
    name: str
    sessions: int
    periods_per_week: int
    per_day: dict[str, int]
    available_periods: int
    utilization_pct: float


class RoomUsage(BaseModel):
    room_id: str
    name: str
    room_type: str
    periods_used: int
    available_periods: int
    utilization_pct: float
    per_day: dict[str, int]


class BatchLoad(BaseModel):
    batch_id: str
    name: str
    sessions: int
    periods_per_week: int
    per_day: dict[str, int]
    teaching_periods: int  # teaching periods that exist in the week
    utilization_pct: float


class Analytics(BaseModel):
    teachers: list[TeacherLoad]
    rooms: list[RoomUsage]
    batches: list[BatchLoad]
    total_periods_scheduled: int
    teaching_periods_per_week: int


class ReviewItem(BaseModel):
    """An entry flagged by revalidation after availability changed."""

    entry_id: str
    codes: list[str]
    messages: list[str]


class RevalidationResult(BaseModel):
    report: ValidationReport
    needs_review: list[ReviewItem] = Field(default_factory=list)
