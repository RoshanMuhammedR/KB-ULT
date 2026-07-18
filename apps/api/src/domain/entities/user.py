from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"
    # Reserved for the future split of "tenant created" vs "user set their password".
    INVITED = "invited"


@dataclass(slots=True)
class User:
    """A tenant's user. Exactly one per tenant today; email is unique within the tenant."""

    tenant_id: UUID
    email: str
    password_hash: str
    id: UUID = field(default_factory=uuid4)
    status: UserStatus = UserStatus.ACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
