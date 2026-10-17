"""SmartSlot scheduling engine - pure Python, no web or database imports.

Public API::

    from app.engine import generate, validate, validate_move, validate_place
    from app.engine import suggest_slots, analytics, expand_sessions, revalidate

``generate(dataset)`` returns a :class:`ScheduleResult`; everything else works
on a ``Dataset`` plus a list of ``Entry`` objects and never mutates its inputs.
"""

from .analytics import analytics
from .expand import expand_sessions
from .loaders import DatasetLoadError, load_dataset_from_dir
from .models import (
    CONFLICT_CODES,
    Analytics,
    AvailabilityRule,
    Batch,
    Config,
    Conflict,
    Dataset,
    Entry,
    MoveResult,
    PeriodDef,
    Requirement,
    RevalidationResult,
    Room,
    ScheduleResult,
    SearchStats,
    Session,
    Subject,
    Suggestion,
    Teacher,
    UnscheduledItem,
    ValidationReport,
)
from .revalidation import add_unavailability, revalidate
from .scheduler import DEFAULT_MAX_NODES, DEFAULT_TIME_LIMIT_S, generate
from .suggest import (
    UnknownEntryError,
    UnknownSessionError,
    suggest_slots,
    validate_move,
    validate_place,
)
from .validator import validate

__all__ = [
    "CONFLICT_CODES",
    "DEFAULT_MAX_NODES",
    "DEFAULT_TIME_LIMIT_S",
    "Analytics",
    "AvailabilityRule",
    "Batch",
    "Config",
    "Conflict",
    "Dataset",
    "DatasetLoadError",
    "Entry",
    "MoveResult",
    "PeriodDef",
    "Requirement",
    "RevalidationResult",
    "Room",
    "ScheduleResult",
    "SearchStats",
    "Session",
    "Subject",
    "Suggestion",
    "Teacher",
    "UnknownEntryError",
    "UnknownSessionError",
    "UnscheduledItem",
    "ValidationReport",
    "add_unavailability",
    "analytics",
    "expand_sessions",
    "generate",
    "load_dataset_from_dir",
    "revalidate",
    "suggest_slots",
    "validate",
    "validate_move",
    "validate_place",
]
