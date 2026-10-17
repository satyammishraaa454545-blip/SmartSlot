"""Version endpoints: generate, list, detail, validate, publish, restore, compare, analytics."""

from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Body, Depends, Response

from ..db import get_conn
from ..engine import analytics
from ..repo import versions as version_repo
from ..requests import GenerateIn, PublishIn, RestoreIn
from ..schemas import (
    AnalyticsOut,
    CompareOut,
    GenerateResponse,
    PublishResponse,
    RestoreResponse,
    ValidateResponse,
    VersionDetail,
    VersionMeta,
)
from ..services import compare as compare_svc
from ..services import versions as svc
from ..services.state import build_detail, load_dataset_for, load_version_row

router = APIRouter(tags=["versions"])


@router.post("/datasets/{dataset_id}/generate", response_model=GenerateResponse, status_code=201,
             summary="Generate a NEW draft timetable")
def generate(dataset_id: int, body: Optional[GenerateIn] = Body(None), conn: sqlite3.Connection = Depends(get_conn)) -> GenerateResponse:
    """Never touches the published version. 422 `IMPORT_HAS_ERRORS` / `DATASET_EMPTY` when the data is not ready.
    The response is 201 even for a `partial` result: check `result.status`."""
    body = body or GenerateIn()
    return svc.generate_version(conn, dataset_id, max_nodes=body.max_nodes, time_limit_s=body.time_limit_s,
                                label=body.label, notes=body.notes, created_by=body.created_by)


@router.get("/datasets/{dataset_id}/versions", response_model=list[VersionMeta], summary="List versions (newest first)")
def list_versions(dataset_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> list[VersionMeta]:
    return svc.list_versions(conn, dataset_id)


@router.get("/versions/{version_id}", response_model=VersionDetail,
            summary="Full version: entries, unscheduled, validation, summary, needs_review")
def get_version(version_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> VersionDetail:
    return build_detail(conn, version_id)


@router.delete("/versions/{version_id}", status_code=204, summary="Delete a draft or archived version")
def delete_version(version_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    svc.delete_version(conn, version_id)
    return Response(status_code=204)


@router.post("/versions/{version_id}/validate", response_model=ValidateResponse, summary="Re-run the validator")
def validate_version(version_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> ValidateResponse:
    return svc.validate_version(conn, version_id)


@router.post("/versions/{version_id}/revalidate", response_model=ValidateResponse,
             summary="Re-check against the CURRENT availability/room data (flags needs_review)")
def revalidate_version(version_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> ValidateResponse:
    """Same payload as `validate`; use it after changing availability. Works on any version and never modifies it."""
    return svc.validate_version(conn, version_id)


@router.post("/versions/{version_id}/publish", response_model=PublishResponse, summary="Publish a draft")
def publish(version_id: int, body: Optional[PublishIn] = Body(None), conn: sqlite3.Connection = Depends(get_conn)) -> PublishResponse:
    body = body or PublishIn()
    return svc.publish_version(conn, version_id, acknowledge_incomplete=body.acknowledge_incomplete)


@router.post("/versions/{version_id}/restore", response_model=RestoreResponse, status_code=201,
             summary="Clone any version into a new draft")
def restore(version_id: int, body: Optional[RestoreIn] = Body(None), conn: sqlite3.Connection = Depends(get_conn)) -> RestoreResponse:
    body = body or RestoreIn()
    return svc.restore_version(conn, version_id, label=body.label, notes=body.notes, created_by=body.created_by)


@router.get("/versions/{a}/compare/{b}", response_model=CompareOut, summary="What changed from version a to version b")
def compare(a: int, b: int, conn: sqlite3.Connection = Depends(get_conn)) -> CompareOut:
    return compare_svc.compare_versions(conn, a, b)


@router.get("/versions/{version_id}/analytics", response_model=AnalyticsOut,
            summary="Teacher workload, room utilisation, batch load")
def version_analytics(version_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> AnalyticsOut:
    row = load_version_row(conn, version_id)
    dataset = load_dataset_for(conn, row["dataset_id"])
    result = analytics(dataset, version_repo.load_entries(conn, version_id))
    return AnalyticsOut(version_id=version_id, **result.model_dump())
