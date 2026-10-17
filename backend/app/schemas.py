"""Response models of the public API (see docs/API.md).

Everything the frontend needs is included, enriched with display names and
times, so the UI never has to join ids against other lists.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .engine.models import (
    AvailabilityRule,
    Batch,
    BatchLoad,
    Involved,
    PeriodDef,
    Requirement,
    Room,
    RoomUsage,
    SearchStats,
    Subject,
    Teacher,
    TeacherLoad,
)
from .importer.report import ImportReport

VersionStatus = Literal["draft", "published", "archived"]
ValidationStatus = Literal["valid_complete", "valid_incomplete", "invalid"]


# --------------------------------------------------------------------------
# Timetable building blocks
# --------------------------------------------------------------------------
class EntryOut(BaseModel):
    entry_id: str  # == session_id
    session_id: str
    day: str  # Mon..Sun
    start_period: int
    end_period: int  # last period occupied (start_period + duration - 1)
    duration: int
    start_time: Optional[str] = None  # "09:00" (start of start_period)
    end_time: Optional[str] = None  # "10:40" (end of end_period)
    subject_id: str
    subject_name: str
    subject_type: str  # lecture | practical
    batch_id: str
    batch_name: str
    teacher_id: str
    teacher_name: str
    room_id: str
    room_name: str
    room_type: str  # classroom | lab | "" when the room id is unknown
    needs_review: bool = False  # now clashes with the current availability / room data
    review_messages: list[str] = Field(default_factory=list)


class SuggestionOut(BaseModel):
    day: str
    start_period: int
    end_period: int
    duration: int
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    room_id: str
    room_name: str
    teacher_id: Optional[str] = None
    teacher_name: Optional[str] = None
    label: str  # "Tuesday Period 3 in Room 102"


class ConflictOut(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str
    day: Optional[str] = None
    period: Optional[int] = None
    entry_ids: list[str] = Field(default_factory=list)
    involved: Involved = Field(default_factory=Involved)
    suggestions: list[SuggestionOut] = Field(default_factory=list)
    suggested_entry_id: Optional[str] = None


class ValidationOut(BaseModel):
    valid: bool
    complete: bool
    status: ValidationStatus
    error_count: int
    warning_count: int
    counts: dict[str, int]
    summary: str
    conflicts: list[ConflictOut]


class UnscheduledOut(BaseModel):
    session_id: str
    subject_id: str
    subject_name: str
    subject_type: str
    batch_id: str
    batch_name: str
    teacher_id: str
    teacher_name: str
    duration: int
    index: int  # this is session `index` of `of` for the (subject, batch)
    of: int
    reasons: list[str]
    reason_codes: list[str]
    hints: list[str]


class ReviewOut(BaseModel):
    entry_id: str
    label: str  # "Data Structures for CE-A (Mon Period 3)"
    codes: list[str]
    messages: list[str]


class MoveResultOut(BaseModel):
    valid: bool
    message: str
    entry: Optional[EntryOut] = None  # the proposed placement
    conflicts: list[ConflictOut] = Field(default_factory=list)
    affected_entries: list[EntryOut] = Field(default_factory=list)
    suggestions: list[SuggestionOut] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Versions
# --------------------------------------------------------------------------
class SummaryOut(BaseModel):
    total_sessions: int
    scheduled: int
    unscheduled: int
    status: ValidationStatus
    error_count: int
    warning_count: int
    needs_review_count: int
    message: str  # one plain-English sentence for the status badge


class VersionMeta(BaseModel):
    id: int
    dataset_id: int
    seq: int  # 1, 2, 3 ... per dataset
    status: VersionStatus
    status_label: str  # "Draft" | "Published" | "Published (incomplete)" | "Archived"
    label: str
    source: str  # generated | restored
    created_at: str
    created_by: str
    published_at: Optional[str] = None
    is_complete: bool
    parent_version_id: Optional[int] = None
    notes: str = ""
    summary: SummaryOut


class GenerationOut(BaseModel):
    status: Literal["complete", "partial", "failed"]
    message: str
    findings: list[str] = Field(default_factory=list)
    stats: SearchStats


class DatasetBrief(BaseModel):
    id: int
    name: str
    semester: str
    days: list[str]
    periods: list[PeriodDef]


class VersionDetail(VersionMeta):
    entries: list[EntryOut]
    unscheduled: list[UnscheduledOut]
    validation: ValidationOut
    needs_review: list[ReviewOut]
    dataset: DatasetBrief
    generation: Optional[GenerationOut] = None


class GenerateResponse(BaseModel):
    version: VersionDetail
    result: GenerationOut


class EditResponse(BaseModel):
    message: str
    entry: Optional[EntryOut] = None  # the entry after the change (None after unschedule)
    version: VersionDetail


class ValidateResponse(BaseModel):
    version_id: int
    summary: SummaryOut
    validation: ValidationOut
    needs_review: list[ReviewOut]


class PublishResponse(BaseModel):
    version: VersionDetail
    archived_version_id: Optional[int] = None  # the previously published version, now archived
    message: str


class RestoreResponse(BaseModel):
    version: VersionDetail
    message: str


class ChangeOut(BaseModel):
    type: Literal["added", "removed", "moved", "room_changed", "teacher_changed", "changed"]
    aspects: list[Literal["moved", "room_changed", "teacher_changed"]] = Field(default_factory=list)
    session_id: str
    subject_id: str
    subject_name: str
    batch_id: str
    batch_name: str
    text: str  # "CS201 for CE-A moved Mon P1 → Tue P3"
    before: Optional[EntryOut] = None
    after: Optional[EntryOut] = None


class CompareSummary(BaseModel):
    added: int
    removed: int
    moved: int
    room_changed: int
    teacher_changed: int
    unchanged: int
    changed_total: int


class VersionRef(BaseModel):
    id: int
    label: str
    status: VersionStatus
    status_label: str


class CompareOut(BaseModel):
    from_version: VersionRef
    to_version: VersionRef
    summary: CompareSummary
    changes: list[ChangeOut]


class AnalyticsOut(BaseModel):
    version_id: int
    teachers: list[TeacherLoad]
    rooms: list[RoomUsage]
    batches: list[BatchLoad]
    total_periods_scheduled: int
    teaching_periods_per_week: int


# --------------------------------------------------------------------------
# Datasets
# --------------------------------------------------------------------------
class DatasetSummary(BaseModel):
    id: int
    name: str
    semester: str
    source: str  # upload | sample:<kind>
    import_status: Literal["ok", "has_errors"]
    created_at: str
    updated_at: str
    counts: dict[str, int]
    error_count: int
    warning_count: int
    total_sessions: int
    version_count: int
    published_version_id: Optional[int] = None


class DatasetDetail(DatasetSummary):
    import_report: ImportReport
    teachers: list[Teacher]
    subjects: list[Subject]
    batches: list[Batch]
    rooms: list[Room]
    requirements: list[Requirement]
    days: list[str]
    periods: list[PeriodDef]
    teaching_periods: list[int]
    availability: list[AvailabilityRule]


class ImportResponse(BaseModel):
    dataset: DatasetSummary
    import_report: ImportReport
    can_generate: bool  # False while import errors exist


class DatasetEditResponse(BaseModel):
    dataset: DatasetDetail
    warnings: list[str] = Field(default_factory=list)
