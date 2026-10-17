"""Version life cycle: generate -> draft -> publish -> archive, restore, delete.

Rules (docs/ARCHITECTURE.md "Versions & publishing"):
  * generating always creates a NEW draft; the published version is untouched;
  * publishing needs a clean validation; unscheduled sessions need an explicit
    acknowledgement and make the version "incomplete";
  * publishing archives (never deletes) the previously published version;
  * any version can be restored into a new draft.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from ..db import transaction
from ..engine import generate
from ..engine.models import Dataset
from ..errors import ApiError, not_found
from ..repo import datasets as dataset_repo
from ..repo import versions as version_repo
from ..schemas import (
    GenerateResponse,
    GenerationOut,
    PublishResponse,
    RestoreResponse,
    ValidateResponse,
    VersionMeta,
)
from .enrich import Enricher
from .state import (
    build_detail,
    build_meta,
    compute_state,
    load_dataset_for,
    load_state,
    load_version_row,
)


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------
def _block_reasons(dataset: Dataset) -> list[str]:
    missing = []
    if not dataset.requirements:
        missing.append("there are no weekly requirements")
    if not dataset.config.days:
        missing.append("no working days are defined")
    if not any(not p.is_break for p in dataset.config.periods):
        missing.append("there are no teaching periods")
    if not dataset.rooms:
        missing.append("there are no rooms")
    if not dataset.teachers:
        missing.append("there are no teachers")
    return missing


def generate_version(
    conn: sqlite3.Connection,
    dataset_id: int,
    *,
    max_nodes: Optional[int],
    time_limit_s: Optional[float],
    label: Optional[str],
    notes: str,
    created_by: str,
) -> GenerateResponse:
    row = dataset_repo.get_row(conn, dataset_id)
    if row is None:
        raise not_found("dataset", dataset_id)
    report = dataset_repo.report_of(row)
    if row["import_status"] == "has_errors":
        first = [i for i in report.issues if i.severity == "error"][:3]
        examples = "; ".join(
            f"{i.file}{f' row {i.row}' if i.row else ''}: {i.message}" for i in first
        )
        raise ApiError(
            422, "IMPORT_HAS_ERRORS",
            f"This dataset has {report.error_count} import error(s), so a timetable cannot be generated yet. "
            f"Fix the CSV files and import them again. First problems: {examples}",
            error_count=report.error_count, warning_count=report.warning_count,
        )
    dataset = dataset_repo.load_dataset(conn, dataset_id)
    missing = _block_reasons(dataset)
    if missing:
        raise ApiError(
            422, "DATASET_EMPTY",
            "A timetable cannot be generated because " + " and ".join(missing) + ". Import a complete dataset first.",
        )

    kwargs: dict = {}
    if max_nodes is not None:
        kwargs["max_nodes"] = max_nodes
    if time_limit_s is not None:
        kwargs["time_limit_s"] = time_limit_s
    result = generate(dataset, **kwargs)  # CPU-bound, no DB transaction is held meanwhile

    generation = GenerationOut(
        status=result.status, message=result.message, findings=list(result.findings), stats=result.stats
    )
    with transaction(conn):
        version_id, _seq, _label = version_repo.insert_version(
            conn, dataset_id=dataset_id, label=label, source="generated", created_by=created_by,
            parent_version_id=None, notes=notes, is_complete=result.status == "complete",
            generation_result=generation.model_dump(),
        )
        version_repo.insert_entries(conn, version_id, result.scheduled)
        version_repo.insert_unscheduled(conn, version_id, version_repo.notes_from_result(result.unscheduled))
    return GenerateResponse(version=build_detail(conn, version_id), result=generation)


# ---------------------------------------------------------------------------
# listing
# ---------------------------------------------------------------------------
def list_versions(conn: sqlite3.Connection, dataset_id: int) -> list[VersionMeta]:
    if dataset_repo.get_row(conn, dataset_id) is None:
        raise not_found("dataset", dataset_id)
    dataset = dataset_repo.load_dataset(conn, dataset_id)
    out = []
    for row in version_repo.list_rows(conn, dataset_id):
        state = compute_state(dataset, version_repo.load_entries(conn, row["id"]), with_suggestions=False)
        out.append(build_meta(row, state))
    return out


def validate_version(conn: sqlite3.Connection, version_id: int) -> ValidateResponse:
    row = load_version_row(conn, version_id)
    state = load_state(conn, row)
    by_id = {e.session_id: e for e in state.entries}
    enricher = state.enricher
    return ValidateResponse(
        version_id=version_id,
        summary=state.summary(),
        validation=enricher.validation(state.report),
        needs_review=[enricher.review(state.review[k], by_id) for k in sorted(state.review)],
    )


# ---------------------------------------------------------------------------
# publish / restore / delete
# ---------------------------------------------------------------------------
def publish_version(conn: sqlite3.Connection, version_id: int, *, acknowledge_incomplete: bool) -> PublishResponse:
    archived_id: Optional[int] = None
    with transaction(conn):  # one write lock for check + switch: nothing half-published
        row = load_version_row(conn, version_id)
        if row["status"] == "published":
            raise ApiError(409, "ALREADY_PUBLISHED", f"{row['label']} is already the published version.",
                           version_id=version_id)
        if row["status"] == "archived":
            raise ApiError(409, "VERSION_NOT_EDITABLE",
                           f"{row['label']} is archived. Restore it to a draft first "
                           f"(POST /api/versions/{version_id}/restore), then publish the draft.",
                           version_id=version_id, status="archived")
        state = load_state(conn, row)
        if not state.report.valid:
            enricher = state.enricher
            raise ApiError(
                409, "PUBLISH_BLOCKED",
                f"{row['label']} cannot be published: {state.report.error_count} "
                f"{'conflict' if state.report.error_count == 1 else 'conflicts'} must be fixed first. "
                f"{state.report.conflicts[0].message}",
                validation=enricher.validation(state.report).model_dump(),
            )
        unscheduled = state.total_sessions - len(state.entries)
        if unscheduled > 0 and not acknowledge_incomplete:
            raise ApiError(
                409, "ACKNOWLEDGE_INCOMPLETE",
                f"{unscheduled} of {state.total_sessions} required session(s) are not scheduled. Publishing would "
                "mark this timetable as incomplete. Send acknowledge_incomplete=true to publish it anyway.",
                unscheduled=unscheduled, total_sessions=state.total_sessions,
            )
        previous = version_repo.published_row(conn, row["dataset_id"])
        archived_id = previous["id"] if previous else None
        version_repo.archive_published(conn, row["dataset_id"])
        version_repo.mark_published(conn, version_id, is_complete=unscheduled == 0)
    detail = build_detail(conn, version_id)
    note = " (incomplete: some sessions are unscheduled)" if unscheduled else ""
    return PublishResponse(version=detail, archived_version_id=archived_id,
                           message=f"{detail.label} is now the published timetable{note}.")


def restore_version(
    conn: sqlite3.Connection, version_id: int, *, label: Optional[str], notes: str, created_by: str
) -> RestoreResponse:
    """Clone any version into a NEW draft (the source is never changed)."""
    with transaction(conn):
        source = load_version_row(conn, version_id)
        entries = version_repo.load_entries(conn, version_id)
        dataset = load_dataset_for(conn, source["dataset_id"])
        total = len(Enricher(dataset).sessions)
        seq = version_repo.next_seq(conn, source["dataset_id"])
        new_label = (label or "").strip() or f"Version {seq} (restored from {source['label']})"
        new_id, _seq, _label = version_repo.insert_version(
            conn, dataset_id=source["dataset_id"], label=new_label, source="restored", created_by=created_by,
            parent_version_id=version_id, notes=notes, is_complete=len(entries) >= total, generation_result=None,
        )
        version_repo.insert_entries(conn, new_id, entries)
        placed = {e.session_id for e in entries}
        notes_by_session = version_repo.load_unscheduled_notes(conn, version_id)
        version_repo.insert_unscheduled(
            conn, new_id, [n for sid, n in notes_by_session.items() if sid not in placed]
        )
    detail = build_detail(conn, new_id)
    return RestoreResponse(
        version=detail,
        message=f"Created {detail.label} as a new draft. {detail.summary.message}",
    )


def delete_version(conn: sqlite3.Connection, version_id: int) -> None:
    with transaction(conn):
        row = load_version_row(conn, version_id)
        if row["status"] == "published":
            raise ApiError(409, "CANNOT_DELETE_PUBLISHED",
                           f"{row['label']} is the published timetable and cannot be deleted. "
                           "Publish another version first.", version_id=version_id)
        version_repo.delete_version(conn, version_id)

