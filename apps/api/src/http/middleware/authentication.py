"""Authentication middleware — establishes *who* is calling, and nothing else.

This layer owns credential handling: it runs a chain of ``Authenticator``s, each of which
knows one mechanism (bearer token today; API keys, service accounts, OAuth later). The
first authenticator to recognise its credential wins and yields an ``Identity``, which is
stashed on the ASGI ``scope`` for the tenant-context layer downstream to bind.

Deliberately split from tenant binding: the tenant layer should not grow a new branch every
time a new way of proving identity is added. Add an ``Authenticator`` here instead.

Implemented as **pure ASGI** (not ``BaseHTTPMiddleware``) so it shares one context chain
with the tenant-context middleware and the sync threadpool endpoints below it.

Semantics of the chain:
  * An authenticator returns an ``Identity`` → authenticated, chain stops.
  * It returns ``None`` → "my credential isn't present", try the next one.
  * It raises ``AuthError`` → a credential *was* present but invalid → 401 immediately
    (a bad credential is not the same as no credential; we never fall through to a weaker
    authenticator behind it).
  * No authenticator produced an identity → 401.
"""

from __future__ import annotations

import json
from typing import Protocol

from src.core.exceptions import AuthError
from src.core.identity import Identity
from src.domain.interfaces.auth import ITokenService

# Paths that never require authentication: the credential-issuing endpoints (which run
# pre-identity by definition), health, and the API docs. Note this is deliberately NOT the
# whole `/auth` tree — `/auth/me` is authenticated like any other route.
_EXEMPT_PREFIXES = (
    "/auth/login",
    "/auth/register",
    "/auth/google",
    "/auth/refresh",
    "/auth/logout",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)

# ASGI scope key the resolved identity is published under for the tenant-context layer.
SCOPE_IDENTITY_KEY = "kb.identity"


def _is_exempt(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in _EXEMPT_PREFIXES)


class Authenticator(Protocol):
    def authenticate(self, scope) -> Identity | None:
        """Return an ``Identity`` if this mechanism's credential is present and valid,
        ``None`` if it isn't present, or raise ``AuthError`` if present but invalid."""
        ...


class BearerTokenAuthenticator:
    """Authenticates ``Authorization: Bearer <access_token>`` via the token service."""

    def __init__(self, token_service: ITokenService) -> None:
        self.token_service = token_service

    def authenticate(self, scope) -> Identity | None:
        token = _bearer_token(scope)
        if token is None:
            return None
        claims = self.token_service.decode_access_token(token)  # raises AuthError
        return Identity(tenant_id=claims.tenant_id, user_id=claims.user_id)


class AuthenticationMiddleware:
    def __init__(self, app, authenticators: list[Authenticator]) -> None:
        self.app = app
        self.authenticators = authenticators

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or _is_exempt(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        try:
            identity = self._authenticate(scope)
        except AuthError as exc:
            await _unauthorized(send, str(exc))
            return

        if identity is None:
            await _unauthorized(send, "Authentication required")
            return

        scope[SCOPE_IDENTITY_KEY] = identity
        await self.app(scope, receive, send)

    def _authenticate(self, scope) -> Identity | None:
        for authenticator in self.authenticators:
            identity = authenticator.authenticate(scope)  # raises AuthError if invalid
            if identity is not None:
                return identity
        return None


def _bearer_token(scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            decoded = value.decode("latin-1")
            if decoded.lower().startswith("bearer "):
                return decoded[7:].strip()
    return None


async def _unauthorized(send, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
