"""All HTTP routes, mounted under ``/api``."""

from fastapi import APIRouter

from . import datasets, editing, exports, system, versions

api_router = APIRouter(prefix="/api")
for _module in (system, datasets, versions, editing, exports):
    api_router.include_router(_module.router)

__all__ = ["api_router"]
