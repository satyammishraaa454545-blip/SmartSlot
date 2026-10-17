"""Live state of a stored version: validation, review flags, summary, full detail.

Validation is always recomputed from the stored entries against the dataset as
it is *now*, so a published version that is later affected by an availability
change shows up as ``invalid`` / ``needs_review`` without ever being modified.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from ..engine import revalidate, validate
from ..engine.models import Dataset, Entry, ReviewItem, ValidationReport
from ..errors import ApiError, not_found
from ..repo import datasets as dataset_repo
from ..repo import versions as version_repo
from ..schemas import (
    DatasetBrief,
    GenerationOut,
    SummaryOut,
    VersionDetail,
    VersionMeta,
)
from .enrich import Enricher


def status_label(status: str, is_complete: bool) -> str:
    if status == "published":
        return "Published" if is_complete else "Published (incomplete)"
    return status.capitalize()


def load_version_row(conn: sqlite3.Connection, version_id: int) -> sqlite3.Row:
    row = version_repo.get_row(conn, version_id)
    if row is None:
        raise not_found("version", version_id)
    return row


def load_dataset_for(conn: sqlite3.Connection, dataset_id: int) -> Dataset:
    try:
        return dataset_repo.load_dataset(conn, dataset_id)
    except KeyError:
        raise not_found("dataset", dataset_id) from None


def require_draft(row: sqlite3.Row) -> None:
    if row["status"] != "draft":
        state = "published" if row["status"] == "published" else "archived"
        raise ApiError(
            409, "VERSION_NOT_EDITABLE",
            f"{row['label']} is {state} and cannot be edited. Restore it to a new draft first "
            f"(POST /api/versions/{row['id']}/restore), then make your changes in the draft.",
            version_id=row["id"], status=row["status"],
        )


@dataclass
class VersionState:
    """Everything derived from (dataset, entries) in one validator pass."""

    dataset: Dataset
    entries: list[Entry]
    report: ValidationReport
    review: dict[str, ReviewItem]
    enricher: Enricher

    @property
    def total_sessions(self) -> int:
        return len(self.enricher.sessions)

    def summary(self) -> SummaryOut:
        scheduled = len(self.entries)
        total = self.total_sessions
        return SummaryOut(
            total_sessions=total,
            scheduled=scheduled,
            unscheduled=max(total - scheduled, 0),
            status=self.report.status,
            error_count=self.report.error_count,
            warning_count=self.report.warning_count,
            needs_review_count=len(self.review),
            message=self.report.summary,
        )


def compute_state(dataset: Dataset, entries: list[Entry], *, with_suggestions: bool = True) -> VersionState:
    """Validate ``entries`` and work out which of them need a coordinator's review."""
    enricher = Enricher(dataset)
    if with_suggestions:
        result = revalidate(dataset, entries)  # engine: report + availability-based review flags
        report = result.report
        review = {item.entry_id: item for item in result.needs_review}
    else:
        report = validate(dataset, entries, with_suggestions=False)
        review = {}
    # Any other hard error on a *saved* version can only come from data that
    # changed after the version was made (room capacity/type, periods ...).
    for conflict in report.conflicts:
        if conflict.severity != "error":
            continue
        for entry_id in conflict.entry_ids:
            item = review.setdefault(entry_id, ReviewItem(entry_id=entry_id, codes=[], messages=[]))
            if conflict.code not in item.codes:
                item.codes.append(conflict.code)
            if conflict.message not in item.messages:
                item.messages.append(conflict.message)
    return VersionState(dataset, entries, report, review, enricher)


def load_state(conn: sqlite3.Connection, row: sqlite3.Row, *, with_suggestions: bool = True) -> VersionState:
    dataset = load_dataset_for(conn, row["dataset_id"])
    entries = version_repo.load_entries(conn, row["id"])
    return compute_state(dataset, entries, with_suggestions=with_suggestions)


def meta_fields(row: sqlite3.Row, summary: SummaryOut) -> dict:
    is_complete = bool(row["is_complete"])
    return {
        "id": row["id"], "dataset_id": row["dataset_id"], "seq": row["seq"], "status": row["status"],
        "status_label": status_label(row["status"], is_complete), "label": row["label"],
        "source": row["source"], "created_at": row["created_at"], "created_by": row["created_by"],
        "published_at": row["published_at"], "is_complete": is_complete,
        "parent_version_id": row["parent_version_id"], "notes": row["notes"], "summary": summary,
    }


def build_meta(row: sqlite3.Row, state: VersionState) -> VersionMeta:
    return VersionMeta(**meta_fields(row, state.summary()))


def build_detail(conn: sqlite3.Connection, version_id: int) -> VersionDetail:
    row = load_version_row(conn, version_id)
    state = load_state(conn, row)
    enricher, dataset = state.enricher, state.dataset
    notes = version_repo.load_unscheduled_notes(conn, version_id)
    by_id = {e.session_id: e for e in state.entries}
    generation = json.loads(row["generation_result"]) if row["generation_result"] else None
    return VersionDetail(
        **meta_fields(row, state.summary()),
        entries=enricher.entries(state.entries, state.review),
        unscheduled=enricher.unscheduled(state.entries, notes),
        validation=enricher.validation(state.report),
        needs_review=[enricher.review(state.review[k], by_id) for k in sorted(state.review)],
        dataset=DatasetBrief(
            id=row["dataset_id"], name=dataset.name, semester=dataset.semester,
            days=list(dataset.config.days), periods=list(dataset.config.periods),
        ),
        generation=GenerationOut.model_validate(generation) if generation else None,
    )
