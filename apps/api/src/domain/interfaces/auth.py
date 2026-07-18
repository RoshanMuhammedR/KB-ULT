from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(slots=True)
class AccessTokenClaims:
    """The tenant/user identity carried inside a decoded access token."""

    user_id: UUID
    tenant_id: UUID
    jti: str


class IUnitOfWork(Protocol):
    """Transaction control, so a use case can make several repository writes atomic
    without depending on SQLAlchemy. The request/worker `Session` satisfies it."""

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


class IPasswordHasher(Protocol):
    """Password hashing, kept behind a port so the crypto lib stays in infrastructure."""

    def hash(self, password: str) -> str:
        ...

    def verify(self, password: str, password_hash: str) -> bool:
        """Constant-time-ish verify; returns False (never raises) on a malformed hash."""
        ...


class ITokenService(Protocol):
    """Access-token issue/decode, kept behind a port so JWT stays in infrastructure."""

    def issue_access_token(self, user_id: UUID, tenant_id: UUID) -> tuple[str, int]:
        """Return (signed_jwt, expires_in_seconds)."""
        ...

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        """Decode + verify; raise TokenError if missing/malformed/expired/wrong type."""
        ...
