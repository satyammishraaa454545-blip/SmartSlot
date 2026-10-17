"""Request bodies of the public API.  Unknown fields are rejected so typos are noticed."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
CreatedBy = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


# -- configuration -------------------------------------------------------------
class PeriodIn(Body):
    period: int = Field(ge=1, le=99)
    start: str  # "HH:MM" 24-hour
    end: str
    is_break: bool = False


class ConfigIn(Body):
    days: list[str] = Field(min_length=1, max_length=7)  # Mon..Sun (names like "Monday" are accepted)
    periods: list[PeriodIn] = Field(min_length=1, max_length=48)


class RuleIn(Body):
    resource_id: str = Field(min_length=1, max_length=40)  # a teacher_id or room_id
    day: str
    period: int = Field(ge=1, le=999)
    available: bool = False  # only `false` rules are stored; `true` is the default


class AvailabilityPut(Body):
    rules: list[RuleIn] = Field(max_length=20000)


class AvailabilityBulk(Body):
    changes: list[RuleIn] = Field(min_length=1, max_length=2000)


class RoomPatch(Body):
    name: Optional[Text] = None
    capacity: Optional[int] = Field(default=None, ge=1, le=10000)
    room_type: Optional[Literal["classroom", "lab"]] = None


class TeacherPatch(Body):
    name: Optional[Text] = None
    department_id: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]] = None


class BatchPatch(Body):
    name: Optional[Text] = None
    student_count: Optional[int] = Field(default=None, ge=1, le=10000)
    semester: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]] = None
    department_id: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]] = None


# -- versions ----------------------------------------------------------------------
class GenerateIn(Body):
    max_nodes: Optional[int] = Field(default=None, ge=1, le=5_000_000)
    time_limit_s: Optional[float] = Field(default=None, gt=0, le=120)
    label: Optional[Text] = None
    notes: Notes = ""
    created_by: CreatedBy = "coordinator"


class PublishIn(Body):
    acknowledge_incomplete: bool = False


class RestoreIn(Body):
    label: Optional[Text] = None
    notes: Notes = ""
    created_by: CreatedBy = "coordinator"


class MoveIn(Body):
    """Fields left out (or null) keep their current value."""

    day: Optional[str] = Field(default=None, max_length=20)
    start_period: Optional[int] = Field(default=None, ge=1, le=999)
    room_id: Optional[str] = Field(default=None, max_length=40)
    teacher_id: Optional[str] = Field(default=None, max_length=40)


class PlaceIn(Body):
    day: str = Field(max_length=20)
    start_period: int = Field(ge=1, le=999)
    room_id: str = Field(max_length=40)
    teacher_id: Optional[str] = Field(default=None, max_length=40)
