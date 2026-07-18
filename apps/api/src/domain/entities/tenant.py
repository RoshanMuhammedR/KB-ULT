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
    """The top-level isolation boundary, identified by a globally-unique `domain` slug."""

    domain: str
    name: str = ""
    id: UUID = field(default_factory=uuid4)
    status: TenantStatus = TenantStatus.ACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
