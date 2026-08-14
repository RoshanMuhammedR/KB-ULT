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
    """A tenant's user. `email` is unique **globally**, not per tenant: it is the sole
    credential subject, so a login resolves the user first and the tenant from them.

    `password_hash` is None for accounts created through Google, which have no password.
    `google_sub` is Google's stable subject id, set when an account is created through or
    linked to Google — the two are independent, so an account can have both.

    `email_verified_at` is set immediately for Google sign-ins (Google already verified it)
    and otherwise unused today, since registration activates immediately.
    """

    tenant_id: UUID
    email: str
    password_hash: str | None = None
    google_sub: str | None = None
    name: str = ""
    id: UUID = field(default_factory=uuid4)
    status: UserStatus = UserStatus.ACTIVE
    email_verified_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
