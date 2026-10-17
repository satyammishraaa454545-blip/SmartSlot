"""Revalidation after availability changes.

When a teacher or room becomes unavailable *after* a timetable was generated,
the timetable must not be silently altered.  Instead :func:`revalidate`
re-runs the independent validator against the current dataset and flags every
class that now sits in an unavailable slot as ``needs_review``.
"""

from __future__ import annotations

from collections.abc import Iterable

from .models import (
    AvailabilityRule,
    Dataset,
    Entry,
    ReviewItem,
    RevalidationResult,
)
from .validator import validate

# Conflicts that availability changes can cause.
_AVAILABILITY_CODES = {"TEACHER_UNAVAILABLE", "ROOM_UNAVAILABLE"}


def add_unavailability(
    dataset: Dataset, resource_id: str, slots: Iterable[tuple[str, int]]
) -> Dataset:
    """Return a COPY of ``dataset`` with extra unavailable (day, period) slots.

    ``resource_id`` is a teacher_id or room_id.  The input is not modified.
    """
    extra = [
        AvailabilityRule(resource_id=resource_id, day=day, period=period, available=False)
        for day, period in slots
    ]
    return dataset.model_copy(update={"availability": [*dataset.availability, *extra]})


def revalidate(dataset: Dataset, entries: Iterable[Entry]) -> RevalidationResult:
    """Validate ``entries`` against the (possibly changed) ``dataset``.

    ``needs_review`` lists the entries that are now in an unavailable slot,
    sorted by entry id; ``report`` is the full validation report.
    """
    entries = list(entries)
    report = validate(dataset, entries, with_suggestions=True)
    flagged: dict[str, ReviewItem] = {}
    for c in report.conflicts:
        if c.code not in _AVAILABILITY_CODES:
            continue
        for entry_id in c.entry_ids:
            item = flagged.setdefault(entry_id, ReviewItem(entry_id=entry_id, codes=[], messages=[]))
            if c.code not in item.codes:
                item.codes.append(c.code)
            item.messages.append(c.message)
    return RevalidationResult(
        report=report, needs_review=[flagged[k] for k in sorted(flagged)]
    )
