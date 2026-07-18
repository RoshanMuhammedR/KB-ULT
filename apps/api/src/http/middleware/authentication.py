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

from sqlalchemy import select

from src.core.exceptions import AuthError
from src.core.identity import Identity
from src.core.tenant_context import system_scope
from src.domain.interfaces.auth import ITokenService

# Prefixes that never require authentication: auth (pre-tenant), health, and the API docs.
_EXEMPT_PREFIXES = ("/auth", "/health", "/docs", "/redoc", "/openapi.json")

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


class DefaultTenantAuthenticator:
    """Rollout-only fallback: attributes credential-less requests to the seeded default
    tenant so the pre-auth web client keeps working. Wired in only while
    ``tenancy_default_fallback`` is on; dropping it makes missing credentials a hard 401.

    It never raises, so it can only be the *last* link in the chain — a present-but-invalid
    bearer token has already raised out of ``BearerTokenAuthenticator`` before we get here.
    """

    def __init__(self) -> None:
        self._identity: Identity | None = None

    def authenticate(self, scope) -> Identity | None:
        if self._identity is not None:
            return self._identity
        # tenants/users are not tenant-scoped and there is no context yet, so read the
        # seeded default under system_scope. Resolved once and cached.
        from src.infrastructure.database.models import TenantModel, UserModel
        from src.infrastructure.database.session import SessionLocal

        with system_scope():
            db = SessionLocal()
            try:
                tenant = db.scalar(
                    select(TenantModel).where(TenantModel.domain == "default")
                ) or db.scalar(select(TenantModel).order_by(TenantModel.created_at).limit(1))
                if tenant is None:
                    return None
                user = db.scalar(
                    select(UserModel).where(UserModel.tenant_id == tenant.id).limit(1)
                )
                if user is None:
                    return None
                self._identity = Identity(tenant_id=tenant.id, user_id=user.id)
                return self._identity
            finally:
                db.close()


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
