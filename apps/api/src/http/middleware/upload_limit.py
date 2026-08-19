"""Reject oversized uploads before the body is read.

The size checks that already existed run inside the handler, on `len(file_data)` — after
the whole request has been received and, for the multipart path, after `file.file.read()`
has pulled all of it into memory. That caps *cost* (audio transcription is billed) but not
memory: by the time the check runs, the damage it is meant to prevent has been done, and
the container has a 512 MB limit.

`Content-Length` is available in the request headers before a single byte of the body is
consumed, so this rejects there instead. A client can lie about it — but a lying client only
gets as far as the multipart parser, which spools to disk, and the handler's own check still
covers the honest case. This is about not letting an ordinary large file take the process
down, not about defeating a determined attacker.

Written as a raw ASGI callable rather than `BaseHTTPMiddleware` for the same reason the
other two middlewares here are: no extra task, no extra context copy, and it must be able
to answer without ever waking the app below it.
"""

from __future__ import annotations

import json

import structlog

logger = structlog.get_logger(__name__)

# The paths that accept a request body large enough to matter. Everything else is JSON of a
# few kilobytes, and Pydantic's field limits already bound those.
_GUARDED_PATHS = ("/documents/upload",)


def _megabytes(size_bytes: int) -> str:
    # One decimal below 10 MB so a small limit never reads as "0 MB" in the message.
    megabytes = size_bytes / (1024 * 1024)
    return f"{megabytes:.1f}" if megabytes < 10 else str(round(megabytes))


class UploadSizeLimitMiddleware:
    """413s a request whose declared body size exceeds the configured maximum."""

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not any(path.endswith(guarded) or path == guarded for guarded in _GUARDED_PATHS):
            await self.app(scope, receive, send)
            return

        declared = self._content_length(scope)
        if declared is None or declared <= self.max_bytes:
            await self.app(scope, receive, send)
            return

        logger.info("upload_rejected_too_large", path=path, content_length=declared)
        await self._too_large(send, declared)

    def _content_length(self, scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return None
        return None

    async def _too_large(self, send, declared: int) -> None:
        # Written directly rather than raised: this middleware sits above the exception
        # handling middleware, exactly like the 401 in authentication.py.
        body = json.dumps(
            {
                "detail": (
                    f"This file is {_megabytes(declared)} MB. The limit is "
                    f"{_megabytes(self.max_bytes)} MB."
                )
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
