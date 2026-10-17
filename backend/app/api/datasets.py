"""Dataset endpoints: import, samples, templates, configuration, availability, light editing."""

from __future__ import annotations

import sqlite3
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import settings
from ..db import get_conn
from ..errors import ApiError, not_found
from ..importer import (
    SAMPLE_KINDS,
    SAMPLE_SEMESTER,
    IncomingFile,
    SampleNotFoundError,
    sample_uploads,
    template_csv,
    template_names,
    templates_zip,
)
from ..requests import AvailabilityBulk, AvailabilityPut, BatchPatch, ConfigIn, RoomPatch, RuleIn, TeacherPatch
from ..schemas import DatasetDetail, DatasetEditResponse, DatasetSummary, ImportResponse
from ..services import datasets as svc

router = APIRouter(tags=["datasets"])

SampleKind = Literal["feasible", "infeasible", "invalid"]


def _attachment(content: bytes, media_type: str, filename: str) -> Response:
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------
@router.post("/datasets/import", response_model=ImportResponse, status_code=201, summary="Import CSV files or a zip")
async def import_dataset(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> ImportResponse:
    """Multipart form: any number of CSV files (field name `files`, repeatable; the file's own name,
    e.g. `teachers.csv`, says which file it is) **or** one `.zip`; plus text fields `name` and `semester`.

    Always returns 201 with an `import_report`. If the report has errors the dataset is stored with
    `import_status = "has_errors"` and cannot be used to generate until fixed files are imported again.
    """
    try:
        form = await request.form(max_files=settings.MAX_UPLOAD_FILES, max_fields=20, max_part_size=64 * 1024)
    except StarletteHTTPException as exc:  # malformed multipart, too many files/fields
        raise ApiError(400, "BAD_UPLOAD", "The upload could not be read. Send the files as multipart/form-data "
                       f"(at most {settings.MAX_UPLOAD_FILES} files). Detail: {exc.detail}") from None
    uploads: list[IncomingFile] = []
    name = semester = ""
    try:
        for field, value in form.multi_items():
            if isinstance(value, UploadFile):
                data = await value.read(settings.MAX_FILE_BYTES + 1)
                too_big = len(data) > settings.MAX_FILE_BYTES
                uploads.append(IncomingFile(filename=value.filename or "", data=None if too_big else data,
                                            field=field, too_large=too_big))
            elif field == "name":
                name = str(value).strip()
            elif field == "semester":
                semester = str(value).strip()
    finally:
        await form.close()
    if not uploads:
        raise ApiError(422, "NO_FILES", "No files were uploaded. Send the seven required CSV files "
                       "(teachers, subjects, batches, rooms, requirements, days, periods; availability is optional) "
                       "or a single .zip containing them.")
    if len(name) > 120 or len(semester) > 40:
        raise ApiError(422, "NAME_TOO_LONG", "name may have at most 120 characters and semester at most 40.")
    name = name or "Imported dataset"
    return await run_in_threadpool(svc.import_dataset, conn, uploads, name=name, semester=semester, source="upload")


@router.post("/datasets/load-sample", response_model=ImportResponse, status_code=201,
             summary="Load a bundled sample dataset")
def load_sample(
    kind: SampleKind = Query(..., description="feasible | infeasible | invalid"),
    name: Optional[str] = Query(None, max_length=120),
    conn: sqlite3.Connection = Depends(get_conn),
) -> ImportResponse:
    """Reads `sample_data/<kind>/` through the normal importer, so samples get full validation.
    `invalid` deliberately contains 35 errors and is stored with `import_status = "has_errors"`."""
    try:
        uploads = sample_uploads(kind)
    except SampleNotFoundError as exc:
        raise ApiError(500, "SAMPLE_MISSING", f"The sample data is not installed: {exc}") from None
    assert uploads is not None
    return svc.import_dataset(conn, uploads, name=(name or SAMPLE_KINDS[kind]).strip(),
                              semester=SAMPLE_SEMESTER, source=f"sample:{kind}")


# ---------------------------------------------------------------------------
# list / get / delete
# ---------------------------------------------------------------------------
@router.get("/datasets", response_model=list[DatasetSummary], summary="List datasets (newest first)")
def list_datasets(conn: sqlite3.Connection = Depends(get_conn)) -> list[DatasetSummary]:
    return svc.list_summaries(conn)


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail, summary="Dataset with all records and its import report")
def get_dataset(dataset_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> DatasetDetail:
    return svc.detail_of(conn, dataset_id)


@router.delete("/datasets/{dataset_id}", status_code=204, summary="Delete a dataset and all its versions")
def delete_dataset(
    dataset_id: int,
    force: bool = Query(False, description="Required when the dataset has a published timetable"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Response:
    svc.delete_dataset(conn, dataset_id, force=force)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------
@router.get("/templates", response_model=list[str], summary="Names of the CSV templates")
def list_templates() -> list[str]:
    return template_names()


@router.get("/templates.zip", summary="All blank CSV templates in one zip")
def download_templates_zip() -> Response:
    return _attachment(templates_zip(), "application/zip", "smartslot-templates.zip")


@router.get("/templates/{name}.csv", summary="One blank, header-only CSV template")
def download_template(name: str) -> Response:
    content = template_csv(name)
    if content is None:
        raise not_found("template", name)
    return _attachment(content, "text/csv; charset=utf-8", f"{name}.csv")


# ---------------------------------------------------------------------------
# configuration, availability, light editing
# ---------------------------------------------------------------------------
@router.put("/datasets/{dataset_id}/config", response_model=DatasetEditResponse, summary="Replace working days and periods")
def update_config(dataset_id: int, body: ConfigIn, conn: sqlite3.Connection = Depends(get_conn)) -> DatasetEditResponse:
    return svc.update_config(conn, dataset_id, body)


@router.put("/datasets/{dataset_id}/availability", response_model=DatasetEditResponse,
            summary="Replace the whole availability list")
def put_availability(dataset_id: int, body: AvailabilityPut, conn: sqlite3.Connection = Depends(get_conn)) -> DatasetEditResponse:
    return svc.replace_availability(conn, dataset_id, body)


@router.patch("/datasets/{dataset_id}/availability", response_model=DatasetEditResponse,
              summary="Toggle ONE (resource, day, period) slot")
def patch_availability(dataset_id: int, body: RuleIn, conn: sqlite3.Connection = Depends(get_conn)) -> DatasetEditResponse:
    """`available=false` marks the slot unavailable, `available=true` removes the rule again."""
    return svc.toggle_availability(conn, dataset_id, [body])


@router.patch("/datasets/{dataset_id}/availability/bulk", response_model=DatasetEditResponse,
              summary="Toggle many slots at once (all or nothing)")
def patch_availability_bulk(dataset_id: int, body: AvailabilityBulk, conn: sqlite3.Connection = Depends(get_conn)) -> DatasetEditResponse:
    return svc.bulk_availability(conn, dataset_id, body)


@router.patch("/datasets/{dataset_id}/rooms/{room_id}", response_model=DatasetEditResponse, summary="Edit a room")
def patch_room(dataset_id: int, room_id: str, body: RoomPatch, conn: sqlite3.Connection = Depends(get_conn)) -> DatasetEditResponse:
    return svc.patch_entity(conn, dataset_id, "rooms", "room_id", room_id, body, "room")


@router.patch("/datasets/{dataset_id}/teachers/{teacher_id}", response_model=DatasetEditResponse, summary="Edit a teacher")
def patch_teacher(dataset_id: int, teacher_id: str, body: TeacherPatch, conn: sqlite3.Connection = Depends(get_conn)) -> DatasetEditResponse:
    return svc.patch_entity(conn, dataset_id, "teachers", "teacher_id", teacher_id, body, "teacher")


@router.patch("/datasets/{dataset_id}/batches/{batch_id}", response_model=DatasetEditResponse, summary="Edit a batch")
def patch_batch(dataset_id: int, batch_id: str, body: BatchPatch, conn: sqlite3.Connection = Depends(get_conn)) -> DatasetEditResponse:
    return svc.patch_entity(conn, dataset_id, "batches", "batch_id", batch_id, body, "batch")
