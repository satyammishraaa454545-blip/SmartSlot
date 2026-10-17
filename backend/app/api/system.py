"""Health check and the development-only reset."""

from __future__ import annotations

import sqlite3
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from .. import settings
from ..db import get_conn, wipe_all
from ..errors import ApiError
from ..importer import SAMPLE_KINDS, SAMPLE_SEMESTER, sample_uploads
from ..schemas import DatasetSummary
from ..services import datasets as dataset_svc

router = APIRouter(tags=["system"])


class HealthOut(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    dev_mode: bool
    database: str


class ResetOut(BaseModel):
    reset: bool
    dataset: Optional[DatasetSummary] = None


@router.get("/health", response_model=HealthOut, summary="Is the server up?")
def health(conn: sqlite3.Connection = Depends(get_conn)) -> HealthOut:
    conn.execute("SELECT 1")
    return HealthOut(status="ok", service="smartslot-api", version="0.2.0", dev_mode=settings.dev_mode(),
                     database=settings.db_path().name)


@router.post("/dev/reset", response_model=ResetOut, summary="DEV ONLY: wipe the database (optionally load a sample)")
def dev_reset(
    sample: Optional[Literal["feasible", "infeasible", "invalid"]] = Query(None, description="Load this sample after wiping"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> ResetOut:
    """Only works when the server was started with the environment variable `SMARTSLOT_DEV=1`
    (the `start.ps1` script does that); otherwise 404."""
    if not settings.dev_mode():
        raise ApiError(404, "DEV_ONLY", "Reset is disabled. Start the server with SMARTSLOT_DEV=1 to enable it.")
    wipe_all(conn)
    summary = None
    if sample is not None:
        uploads = sample_uploads(sample)
        assert uploads is not None
        response = dataset_svc.import_dataset(conn, uploads, name=SAMPLE_KINDS[sample], semester=SAMPLE_SEMESTER,
                                              source=f"sample:{sample}")
        summary = response.dataset
    return ResetOut(reset=True, dataset=summary)
