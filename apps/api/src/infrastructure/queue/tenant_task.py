"""`@tenant_task` — re-establishes tenant context at the start of every background job.

Procrastinate jobs run outside the request cycle, so the contextvars the HTTP middleware
sets do not exist in a worker. Instead, every job payload carries `tenant_id`/`user_id`
explicitly, and this single shared wrapper (applied to all tasks, not repeated per task)
binds them into the context before the task body opens a session or touches a
tenant-scoped table.

**Fail loud:** a job enqueued without `tenant_id`/`user_id` raises immediately rather than
running unscoped — the queue counterpart of the ORM filter's fail-closed rule.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from src.core.tenant_context import reset_tenant_context, set_tenant_context


def tenant_task(fn: Callable) -> Callable:
    def wrapper(**kwargs):
        # Consume the tenant markers; the task body only sees its own args (e.g. asset_id).
        tenant_id = kwargs.pop("tenant_id", None)
        user_id = kwargs.pop("user_id", None)
        if not tenant_id or not user_id:
            raise ValueError(
                f"Task '{getattr(fn, '__name__', 'task')}' was enqueued without "
                "tenant_id/user_id — refusing to run unscoped"
            )
        tokens = set_tenant_context(UUID(str(tenant_id)), UUID(str(user_id)))
        try:
            return fn(**kwargs)
        finally:
            reset_tenant_context(tokens)

    # Don't use functools.wraps: it sets __wrapped__, which would make signature
    # introspection follow through to the inner fn and hide the tenant kwargs.
    wrapper.__name__ = getattr(fn, "__name__", "tenant_task")
    wrapper.__doc__ = fn.__doc__
    return wrapper
