"""Tenant-context middleware — binds the request's already-resolved ``Identity`` to the
ambient contextvars the ORM tenant-filter and RLS hook read.

It is deliberately mechanism-agnostic: it does not decode tokens, look up users, or know
what a bearer token is. Whoever authenticated the request (see ``authentication.py``)
publishes an ``Identity`` on the ASGI ``scope``; this layer's only job is to bind it for
the duration of the request and reset it afterwards. That single responsibility is what
lets the authentication side grow new credential types without touching tenant binding.

Implemented as **pure ASGI** (not Starlette's ``BaseHTTPMiddleware``) on purpose: the app
runs sync endpoints in the anyio threadpool, and contextvars set here propagate into that
thread — but only within the same context chain. ``BaseHTTPMiddleware`` runs the downstream
app in a separate task, which breaks that propagation; pure ASGI keeps one chain.

Requests with no identity (exempt paths like ``/auth`` and ``/health``) simply pass through
unbound — a scoped query then fails closed downstream, which is the intended default-deny.
"""

from __future__ import annotations

from src.core.identity import Identity
from src.core.tenant_context import reset_tenant_context, set_tenant_context
from src.http.middleware.authentication import SCOPE_IDENTITY_KEY


class TenantContextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        identity: Identity | None = (
            scope.get(SCOPE_IDENTITY_KEY) if scope["type"] == "http" else None
        )
        if identity is None:
            await self.app(scope, receive, send)
            return

        tokens = set_tenant_context(identity.tenant_id, identity.user_id)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_tenant_context(tokens)
