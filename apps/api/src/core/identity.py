"""The authenticated principal for a request, independent of *how* it was established.

An ``Identity`` is what an authentication mechanism (a bearer token today; an API key,
service account, or OAuth exchange tomorrow) produces, and what the tenant-context layer
consumes. Keeping it framework- and mechanism-free is the whole point of the split: the
tenant layer binds ``(tenant_id, user_id)`` without caring which credential proved it.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Identity:
    tenant_id: UUID
    user_id: UUID
