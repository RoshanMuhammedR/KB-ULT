from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass(slots=True)
class RefreshToken:
    """A durable, revocable refresh-token record. Only the token's hash is stored;
    reuse of a revoked token revokes the whole `family_id` (rotation-based revocation).
    """

    user_id: UUID
    tenant_id: UUID
    token_hash: str
    family_id: UUID
    expires_at: datetime
    id: UUID = field(default_factory=uuid4)
    revoked_at: datetime | None = None
    created_at: datetime | None = None
