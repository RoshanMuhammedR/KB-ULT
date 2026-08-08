from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


@dataclass(slots=True)
class Tenant:
    """The top-level isolation boundary — a workspace.

    It has no externally-addressable identifier: a tenant is reached only *through* one of
    its users, whose globally-unique email is what a login presents. `name` is a display
    label and is deliberately not unique.
    """

    name: str
    id: UUID = field(default_factory=uuid4)
    status: TenantStatus = TenantStatus.ACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
