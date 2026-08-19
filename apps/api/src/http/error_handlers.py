"""Global fallback translation of domain errors to HTTP responses.

Routes translate their own exceptions explicitly, and that stays: the mapping is most
readable next to the endpoint it belongs to, and the same error legitimately means
different things in different places (a `ValueError` is a 400 on upload and a 404 on
lookup). What routes cannot do is cover the case nobody thought about — a new route, or a
new failure path in an old one, that lets a `KBError` escape. Unhandled, that is a bare 500
with a stack trace in the logs and an unshaped body for the client.

So this is a backstop, not a policy: every handler here fires only when no route caught the
exception first, and each maps to the status that error already means everywhere else in
the codebase.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.exceptions import (
    AuthError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    KBError,
    MissingTenantContextError,
    TokenError,
    UnsupportedSourceTypeError,
)

logger = structlog.get_logger(__name__)


def _json(status_code: int, detail: str) -> JSONResponse:
    # Same body shape FastAPI's HTTPException produces, so a client cannot tell whether an
    # error was translated at the route or here.
    return JSONResponse(status_code=status_code, content={"detail": detail})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(EmailAlreadyExistsError)
    def _email_exists(_: Request, exc: EmailAlreadyExistsError) -> JSONResponse:
        return _json(409, str(exc))

    @app.exception_handler(InvalidCredentialsError)
    @app.exception_handler(TokenError)
    def _unauthorized(_: Request, exc: AuthError) -> JSONResponse:
        # Deliberately echoes the exception text rather than adding detail: the auth service
        # already makes every login failure indistinguishable on purpose (anti-enumeration),
        # and this must not become the place that leaks which factor failed.
        return _json(401, str(exc))

    @app.exception_handler(UnsupportedSourceTypeError)
    def _unsupported_source(_: Request, exc: UnsupportedSourceTypeError) -> JSONResponse:
        return _json(400, str(exc))

    @app.exception_handler(MissingTenantContextError)
    def _missing_tenant(request: Request, exc: MissingTenantContextError) -> JSONResponse:
        # Never the caller's fault: it means a tenant-scoped query ran with no tenant bound,
        # which is a wiring bug in this service. The fail-closed design already stopped the
        # query — this makes sure it is loud rather than a mystery 500.
        logger.error("missing_tenant_context", path=request.url.path, error=str(exc))
        return _json(500, "Internal server error")

    @app.exception_handler(KBError)
    def _kb_error(request: Request, exc: KBError) -> JSONResponse:
        # The catch-all. Anything reaching here is a domain error a route forgot to map, so
        # log it with the path that produced it — that is the signal to go add the explicit
        # translation — and give the client a shaped body instead of a bare 500.
        logger.exception(
            "unhandled_domain_error",
            path=request.url.path,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return _json(500, "Internal server error")
