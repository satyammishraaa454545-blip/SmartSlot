"""Editing endpoints (drafts only): dry-run, move, unschedule, place, suggestions."""

from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..db import get_conn
from ..engine.labels import normalize_day
from ..errors import ApiError
from ..requests import MoveIn, PlaceIn
from ..schemas import EditResponse, MoveResultOut, SuggestionOut
from ..services import editing as svc

router = APIRouter(tags=["editing"])


def _day(value: Optional[str]) -> Optional[str]:
    """`Monday`/`mon` -> `Mon`; unknown names are passed on so the validator can explain them."""
    if value is None:
        return None
    return normalize_day(value) or value


def _require_change(body: MoveIn) -> None:
    if body.day is None and body.start_period is None and body.room_id is None and body.teacher_id is None:
        raise ApiError(422, "NOTHING_TO_CHANGE",
                       "Send at least one of day, start_period, room_id or teacher_id to change.")


@router.post("/versions/{version_id}/entries/{entry_id}/validate-move", response_model=MoveResultOut,
             summary="Dry run: would this change be allowed? (nothing is saved)")
def validate_move(version_id: int, entry_id: str, body: MoveIn, conn: sqlite3.Connection = Depends(get_conn)) -> MoveResultOut:
    """Always 200. Check `valid`; if false, `conflicts`, `affected_entries` and `suggestions` say why."""
    _require_change(body)
    return svc.dry_run_move(conn, version_id, entry_id, day=_day(body.day), start_period=body.start_period,
                            room_id=body.room_id, teacher_id=body.teacher_id)


@router.patch("/versions/{version_id}/entries/{entry_id}", response_model=EditResponse,
              summary="Move / re-room / re-assign a class (saved only if valid)")
def patch_entry(version_id: int, entry_id: str, body: MoveIn, conn: sqlite3.Connection = Depends(get_conn)) -> EditResponse:
    """409 `MOVE_REJECTED` (nothing saved) when the change would create a conflict; `detail` then also
    contains the full MoveResult (`valid`, `entry`, `conflicts`, `affected_entries`, `suggestions`)."""
    _require_change(body)
    return svc.apply_move(conn, version_id, entry_id, day=_day(body.day), start_period=body.start_period,
                          room_id=body.room_id, teacher_id=body.teacher_id)


@router.post("/versions/{version_id}/entries/{entry_id}/unschedule", response_model=EditResponse,
             summary="Take a class off the timetable (it becomes unscheduled)")
def unschedule(version_id: int, entry_id: str, conn: sqlite3.Connection = Depends(get_conn)) -> EditResponse:
    return svc.unschedule_entry(conn, version_id, entry_id)


@router.get("/versions/{version_id}/entries/{entry_id}/suggestions", response_model=list[SuggestionOut],
            summary="Alternative valid slots for a scheduled class")
def entry_suggestions(version_id: int, entry_id: str, limit: int = Query(5, ge=1, le=20),
                      conn: sqlite3.Connection = Depends(get_conn)) -> list[SuggestionOut]:
    return svc.suggestions_for(conn, version_id, entry_id, limit=limit, scheduled=True)


@router.post("/versions/{version_id}/unscheduled/{session_id}/validate-place", response_model=MoveResultOut,
             summary="Dry run: could this unscheduled session go here?")
def validate_place(version_id: int, session_id: str, body: PlaceIn, conn: sqlite3.Connection = Depends(get_conn)) -> MoveResultOut:
    return svc.dry_run_place(conn, version_id, session_id, day=_day(body.day) or body.day,
                             start_period=body.start_period, room_id=body.room_id, teacher_id=body.teacher_id)


@router.post("/versions/{version_id}/unscheduled/{session_id}/place", response_model=EditResponse,
             summary="Place an unscheduled session (saved only if valid)")
def place(version_id: int, session_id: str, body: PlaceIn, conn: sqlite3.Connection = Depends(get_conn)) -> EditResponse:
    return svc.apply_place(conn, version_id, session_id, day=_day(body.day) or body.day,
                           start_period=body.start_period, room_id=body.room_id, teacher_id=body.teacher_id)


@router.get("/versions/{version_id}/unscheduled/{session_id}/suggestions", response_model=list[SuggestionOut],
            summary="Valid slots where an unscheduled session could go")
def unscheduled_suggestions(version_id: int, session_id: str, limit: int = Query(5, ge=1, le=20),
                            conn: sqlite3.Connection = Depends(get_conn)) -> list[SuggestionOut]:
    return svc.suggestions_for(conn, version_id, session_id, limit=limit, scheduled=False)
