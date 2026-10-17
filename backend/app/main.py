"""SmartSlot API.  Run:  ``uvicorn app.main:app --port 8000``  (docs at /docs)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import settings
from .api import api_router
from .db import init_db
from .errors import install_error_handlers
from .middleware import RequestSizeLimitMiddleware

DESCRIPTION = """
Backend of **SmartSlot**, a college timetable scheduler: import ERP-format CSVs with row-level
validation, generate a conflict-free timetable, edit it safely, publish and export it.

* All data comes from CSV files you import (or the bundled samples) - there is no live ERP connection.
* Errors always look like `{"detail": {"code": "...", "message": "plain English", ...}}`.
* Full reference with examples: `docs/API.md`.
"""


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()  # creates backend/data/smartslot.db and the tables on first start
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="SmartSlot API", version="0.2.0", description=DESCRIPTION, lifespan=lifespan)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    install_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
