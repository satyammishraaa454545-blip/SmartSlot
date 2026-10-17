"""Export endpoints: CSV and PDF."""

from __future__ import annotations

import re
import sqlite3
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.concurrency import run_in_threadpool

from ..db import get_conn
from ..errors import ApiError
from ..export import PdfMeta, build_pdf, entries_to_csv, list_entities
from ..services.state import build_detail, load_dataset_for

router = APIRouter(tags=["export"])


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "timetable"


def _download(content: bytes, media_type: str, filename: str) -> Response:
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/versions/{version_id}/export.csv", summary="One row per scheduled class (UTF-8, Excel friendly)")
def export_csv(version_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    detail = build_detail(conn, version_id)
    name = f"smartslot-{_slug(detail.dataset.name)}-{_slug(detail.label)}.csv"
    return _download(entries_to_csv(detail.entries), "text/csv; charset=utf-8", name)


@router.get("/versions/{version_id}/export.pdf", summary="Printable landscape PDF, one page per batch/teacher/room")
async def export_pdf(
    version_id: int,
    view: Literal["batch", "teacher", "room"] = Query("batch"),
    id: Optional[str] = Query(None, description="batch_id / teacher_id / room_id; omit for every one (one page each)"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Response:
    detail = await run_in_threadpool(build_detail, conn, version_id)
    dataset = await run_in_threadpool(load_dataset_for, conn, detail.dataset_id)
    if id is not None and id not in {e.entity_id for e in list_entities(dataset, view)}:
        raise ApiError(404, "ENTITY_NOT_FOUND", f"This dataset has no {view} with id '{id}'.")
    meta = PdfMeta(
        dataset_name=detail.dataset.name, semester=detail.dataset.semester, version_label=detail.label,
        status=detail.status, incomplete=detail.summary.unscheduled > 0,
    )
    pdf = await run_in_threadpool(build_pdf, meta, dataset, detail.entries, view, id)
    suffix = f"-{_slug(id)}" if id else ""
    name = f"smartslot-{_slug(detail.dataset.name)}-{_slug(detail.label)}-{view}{suffix}.pdf"
    return _download(pdf, "application/pdf", name)
