"""Ambient tenant/user context — pure, framework-free primitives.

Lives in `core` (no SQLAlchemy/FastAPI imports) so both the application layer (auth,
use cases) and the infrastructure layer (the SQLAlchemy listeners in
`database/tenancy.py`) can depend on it without crossing the adapter boundary.

The current tenant is carried in a contextvar: set by the HTTP tenant middleware after
decoding the JWT, and by the Procrastinate `@tenant_task` wrapper from the job payload.
Reads fail closed — no tenant set means a `MissingTenantContextError`, never silent
cross-tenant access. Genuinely cross-tenant or pre-auth work runs inside `system_scope`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from src.core.exceptions import MissingTenantContextError

# None means "unset" — reading while unset (outside system_scope) fails closed.
_current_tenant_id: ContextVar[uuid.UUID | None] = ContextVar("current_tenant_id", default=None)
_current_user_id: ContextVar[uuid.UUID | None] = ContextVar("current_user_id", default=None)
# When true, tenant filtering/stamping stands down (see system_scope).
_system_scope: ContextVar[bool] = ContextVar("tenant_system_scope", default=False)


def current_tenant_id() -> uuid.UUID:
    """The tenant for the current request/job, or raise if none is set (fail closed)."""
    tid = _current_tenant_id.get()
    if tid is None:
        raise MissingTenantContextError("No tenant in context for a tenant-scoped operation")
    return tid


def current_user_id() -> uuid.UUID:
    """The user for the current request/job, or raise if none is set (fail closed)."""
    uid = _current_user_id.get()
    if uid is None:
        raise MissingTenantContextError("No user in context for a tenant-scoped operation")
    return uid


def try_current_tenant_id() -> uuid.UUID | None:
    """Non-raising peek — for callers (e.g. logging, cache keys) that tolerate absence."""
    return _current_tenant_id.get()


def in_system_scope() -> bool:
    return _system_scope.get()


def set_tenant_context(tenant_id: uuid.UUID, user_id: uuid.UUID) -> tuple[Token, Token]:
    """Bind current tenant/user; returns tokens to pass to :func:`reset_tenant_context`."""
    return _current_tenant_id.set(tenant_id), _current_user_id.set(user_id)


def reset_tenant_context(tokens: tuple[Token, Token]) -> None:
    tenant_token, user_token = tokens
    _current_tenant_id.reset(tenant_token)
    _current_user_id.reset(user_token)


@contextmanager
def system_scope() -> Iterator[None]:
    """Suspend tenant filtering/stamping for cross-tenant or pre-auth work.

    The single, auditable "cross-tenant door": registration (creating the tenant/user
    before any context exists), login/refresh (reading tenants/users pre-auth),
    migrations, seeds, and a future break-glass path.
    """
    token = _system_scope.set(True)
    try:
        yield
    finally:
        _system_scope.reset(token)
