"""Request-size limit (pure ASGI, so it also catches streaming bodies without Content-Length)."""

from __future__ import annotations

import json
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import settings


# After refusing a body we still read (and discard) up to this much of it. Answering while the client is
# still sending makes many clients lose the 413 response to a connection reset.
DRAIN_LIMIT = 128 * 1024 * 1024


class _TooLarge(Exception):
    pass


async def _drain(receive: Receive, already: int) -> None:
    """Read and throw away the rest of the request body (bounded)."""
    total = already
    while total <= DRAIN_LIMIT:
        message = await receive()
        if message["type"] != "http.request":
            return
        total += len(message.get("body", b""))
        if not message.get("more_body", False):
            return


def _limit_for(scope: Scope) -> int:
    headers = {k.lower(): v for k, v in scope.get("headers", [])}
    content_type = headers.get(b"content-type", b"").lower()
    if content_type.startswith(b"multipart/form-data"):
        return settings.MAX_UPLOAD_REQUEST_BYTES
    return settings.MAX_JSON_REQUEST_BYTES


def _too_large_body(limit: int) -> bytes:
    size = f"{limit // (1024 * 1024)} MB" if limit >= 1024 * 1024 else f"{max(limit // 1024, 1)} KB"
    return json.dumps({"detail": {
        "code": "REQUEST_TOO_LARGE",
        "message": f"The request is larger than the {size} limit and was rejected. "
                   "Upload smaller files (a timetable CSV is normally a few kilobytes).",
    }}).encode()


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS", "DELETE"):
            await self.app(scope, receive, send)
            return
        limit = _limit_for(scope)
        declared: Any = dict(scope.get("headers", [])).get(b"content-length")
        started = False

        async def reject() -> None:
            body = _too_large_body(limit)
            await send({"type": "http.response.start", "status": 413,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})

        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _drain(receive, 0)
            await reject()
            return

        received = 0
        body_complete = False

        async def counting_receive() -> Message:
            nonlocal received, body_complete
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                body_complete = not message.get("more_body", False)
                if received > limit:
                    raise _TooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _TooLarge:
            if not started:
                if not body_complete:
                    await _drain(receive, received)
                await reject()
