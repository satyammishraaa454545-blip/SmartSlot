"""Manual editing of DRAFT versions: dry-run, move, unschedule, place, suggestions.

Safety rules:
  * only drafts can be edited (published/archived -> 409, restore first);
  * a change is applied only if the engine's validator accepts it; otherwise
    nothing is written and the response carries the full MoveResult;
  * check + write happen inside one write transaction, so two concurrent edits
    cannot both pass validation against stale data.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from ..db import transaction
from ..engine import (
    UnknownEntryError,
    UnknownSessionError,
    suggest_slots,
    validate_move,
    validate_place,
)
from ..engine.models import Entry
from ..errors import ApiError
from ..repo import versions as version_repo
from ..schemas import EditResponse, MoveResultOut, SuggestionOut
from .enrich import MANUAL_NOTE_REASON, Enricher
from .state import build_detail, load_dataset_for, load_version_row, require_draft


def _entry_not_found(entry_id: str) -> ApiError:
    return ApiError(404, "ENTRY_NOT_FOUND",
                    f"There is no scheduled class with id '{entry_id}' in this version.", entry_id=entry_id)


def _session_not_found(session_id: str) -> ApiError:
    return ApiError(404, "SESSION_NOT_FOUND",
                    f"There is no required session with id '{session_id}'.", session_id=session_id)


def _rejected(out: MoveResultOut, what: str) -> ApiError:
    """409 whose ``detail`` is the code + message + the complete MoveResult."""
    payload = out.model_dump(exclude={"message"})
    return ApiError(409, "MOVE_REJECTED", f"{what} was not saved. {out.message}", **payload)


def _refresh_complete(conn: sqlite3.Connection, version_id: int, total_sessions: int) -> None:
    placed = len(version_repo.load_entries(conn, version_id))
    version_repo.set_complete(conn, version_id, placed >= total_sessions)


# ---------------------------------------------------------------------------
# moving a scheduled class
# ---------------------------------------------------------------------------
def dry_run_move(
    conn: sqlite3.Connection, version_id: int, entry_id: str, *,
    day: Optional[str], start_period: Optional[int], room_id: Optional[str], teacher_id: Optional[str],
) -> MoveResultOut:
    row = load_version_row(conn, version_id)
    require_draft(row)
    dataset = load_dataset_for(conn, row["dataset_id"])
    entries = version_repo.load_entries(conn, version_id)
    try:
        result = validate_move(dataset, entries, entry_id, new_day=day, new_start=start_period,
                               new_room=room_id, new_teacher=teacher_id)
    except UnknownEntryError:
        raise _entry_not_found(entry_id) from None
    return Enricher(dataset).move_result(result, entry_id)


def apply_move(
    conn: sqlite3.Connection, version_id: int, entry_id: str, *,
    day: Optional[str], start_period: Optional[int], room_id: Optional[str], teacher_id: Optional[str],
) -> EditResponse:
    with transaction(conn):
        row = load_version_row(conn, version_id)
        require_draft(row)
        dataset = load_dataset_for(conn, row["dataset_id"])
        entries = version_repo.load_entries(conn, version_id)
        enricher = Enricher(dataset)
        try:
            result = validate_move(dataset, entries, entry_id, new_day=day, new_start=start_period,
                                   new_room=room_id, new_teacher=teacher_id)
        except UnknownEntryError:
            raise _entry_not_found(entry_id) from None
        if not result.valid or result.entry is None:
            raise _rejected(enricher.move_result(result, entry_id), "The change")
        version_repo.replace_entry(conn, version_id, result.entry)
        proposed = result.entry
    detail = build_detail(conn, version_id)
    saved = next(e for e in detail.entries if e.entry_id == proposed.session_id)
    return EditResponse(message="Change saved. No conflicts.", entry=saved, version=detail)


# ---------------------------------------------------------------------------
# removing a class from the timetable
# ---------------------------------------------------------------------------
def unschedule_entry(conn: sqlite3.Connection, version_id: int, entry_id: str) -> EditResponse:
    with transaction(conn):
        row = load_version_row(conn, version_id)
        require_draft(row)
        dataset = load_dataset_for(conn, row["dataset_id"])
        entries = version_repo.load_entries(conn, version_id)
        current = next((e for e in entries if e.session_id == entry_id), None)
        if current is None:
            raise _entry_not_found(entry_id)
        version_repo.delete_entry(conn, version_id, entry_id)
        version_repo.insert_unscheduled(conn, version_id, [version_repo.UnscheduledNote(
            entry_id, [MANUAL_NOTE_REASON], ["MANUALLY_UNSCHEDULED"],
            ["Choose one of the suggested slots to place it again."])])
        _refresh_complete(conn, version_id, len(Enricher(dataset).sessions))
    label = Enricher(dataset).entry_label(current)
    return EditResponse(message=f"{label} was moved to the unscheduled list.", entry=None,
                        version=build_detail(conn, version_id))


# ---------------------------------------------------------------------------
# placing an unscheduled session
# ---------------------------------------------------------------------------
def dry_run_place(
    conn: sqlite3.Connection, version_id: int, session_id: str, *,
    day: str, start_period: int, room_id: str, teacher_id: Optional[str],
) -> MoveResultOut:
    row = load_version_row(conn, version_id)
    require_draft(row)
    dataset = load_dataset_for(conn, row["dataset_id"])
    entries = version_repo.load_entries(conn, version_id)
    try:
        result = validate_place(dataset, entries, session_id, day, start_period, room_id, teacher_id)
    except UnknownSessionError:
        raise _session_not_found(session_id) from None
    return Enricher(dataset).move_result(result, session_id)


def apply_place(
    conn: sqlite3.Connection, version_id: int, session_id: str, *,
    day: str, start_period: int, room_id: str, teacher_id: Optional[str],
) -> EditResponse:
    with transaction(conn):
        row = load_version_row(conn, version_id)
        require_draft(row)
        dataset = load_dataset_for(conn, row["dataset_id"])
        entries = version_repo.load_entries(conn, version_id)
        enricher = Enricher(dataset)
        try:
            result = validate_place(dataset, entries, session_id, day, start_period, room_id, teacher_id)
        except UnknownSessionError:
            raise _session_not_found(session_id) from None
        if not result.valid or result.entry is None:
            raise _rejected(enricher.move_result(result, session_id), "The placement")
        placed: Entry = result.entry
        version_repo.insert_entries(conn, version_id, [placed])
        version_repo.delete_unscheduled(conn, version_id, session_id)
        _refresh_complete(conn, version_id, len(enricher.sessions))
    detail = build_detail(conn, version_id)
    saved = next(e for e in detail.entries if e.entry_id == placed.session_id)
    return EditResponse(message="Class placed. No conflicts.", entry=saved, version=detail)


# ---------------------------------------------------------------------------
# suggestions
# ---------------------------------------------------------------------------
def suggestions_for(
    conn: sqlite3.Connection, version_id: int, target_id: str, *, limit: int, scheduled: bool
) -> list[SuggestionOut]:
    """Alternative slots for a scheduled entry or an unscheduled session."""
    row = load_version_row(conn, version_id)
    dataset = load_dataset_for(conn, row["dataset_id"])
    entries = version_repo.load_entries(conn, version_id)
    is_placed = any(e.session_id == target_id for e in entries)
    if scheduled and not is_placed:
        raise _entry_not_found(target_id)
    if not scheduled and is_placed:
        raise ApiError(409, "ALREADY_SCHEDULED",
                       f"Session '{target_id}' is already on the timetable; ask for the entry's suggestions instead.",
                       session_id=target_id)
    try:
        found = suggest_slots(dataset, entries, target_id, limit=limit)
    except UnknownSessionError:
        raise (_entry_not_found(target_id) if scheduled else _session_not_found(target_id)) from None
    enricher = Enricher(dataset)
    duration = enricher.sessions[target_id].duration if target_id in enricher.sessions else 1
    return [enricher.suggestion(s, duration) for s in found]
