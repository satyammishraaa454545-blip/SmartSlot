"""API errors.  Every error response looks like::

    {"detail": {"code": "SOME_CODE", "message": "Plain-English explanation", ...extra}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import logging

log = logging.getLogger("smartslot")


class ApiError(Exception):
    """Raise anywhere to return ``{"detail": {"code", "message", **extra}}``."""

    def __init__(self, status_code: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra

    def body(self) -> dict[str, Any]:
        return {"detail": {"code": self.code, "message": self.message, **self.extra}}


def not_found(kind: str, ident: object) -> ApiError:
    return ApiError(404, f"{kind.upper().replace(' ', '_')}_NOT_FOUND", f"No {kind} with id {ident!r} exists.")


_FIELD_FRIENDLY = {"body": "request", "query": "query", "path": "path"}


def _validation_message(errors: list[dict[str, Any]]) -> str:
    parts = []
    for err in errors[:5]:
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        where = ".".join(loc) or "request"
        parts.append(f"{where}: {err.get('msg', 'invalid value')}")
    more = f" (and {len(errors) - 5} more)" if len(errors) > 5 else ""
    return "The request is not valid. " + "; ".join(parts) + more


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_req: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(exc.body()))

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", ()) if p not in ("body", "query", "path")),
             "message": e.get("msg", "invalid value")}
            for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": {
            "code": "VALIDATION_ERROR", "message": _validation_message(exc.errors()), "errors": errors}})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_req: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            code, message = "NOT_FOUND", "That address does not exist on this server."
        elif exc.status_code == 405:
            code, message = "METHOD_NOT_ALLOWED", "That address does not support this HTTP method."
        elif exc.status_code == 413:
            code, message = "REQUEST_TOO_LARGE", "The request is too large."
        else:
            code, message = f"HTTP_{exc.status_code}", str(exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": {"code": code, "message": message}})

    @app.exception_handler(Exception)
    async def _unexpected(_req: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": {
            "code": "INTERNAL_ERROR",
            "message": "Something went wrong on the server. Nothing was saved. Please try again; "
                       "if it keeps happening, check the server log."}})
