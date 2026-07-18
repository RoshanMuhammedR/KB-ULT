"""Cache-key construction — the enforced multi-tenant namespacing convention.

**Every tenant-scoped cache value MUST be keyed via :func:`tenant_cache_key`.** It prefixes
the key with ``tenant:{tenant_id}:`` so one tenant can never read another's cached data,
and it **fails closed** — building a tenant key with no tenant in context raises rather than
producing an ambiguous, cross-tenant key. Genuinely global values use
:func:`system_cache_key` (``system:`` prefix).

Making the key builders the only sanctioned way to construct keys means the namespace is a
structural guarantee, not a thing each call site must remember.
"""

from __future__ import annotations

from src.core.tenant_context import current_tenant_id


def tenant_cache_key(scope: str, *parts: str) -> str:
    """`tenant:{tenant_id}:{scope}:{parts...}` — fails closed if no tenant is in context."""
    tenant_id = current_tenant_id()  # raises MissingTenantContextError when unset
    tail = ":".join(parts)
    base = f"tenant:{tenant_id}:{scope}"
    return f"{base}:{tail}" if tail else base


def system_cache_key(scope: str, *parts: str) -> str:
    """`system:{scope}:{parts...}` — for values that are not tenant-specific."""
    tail = ":".join(parts)
    base = f"system:{scope}"
    return f"{base}:{tail}" if tail else base
