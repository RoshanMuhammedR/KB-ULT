"""Authentication use cases: register, login, refresh, logout.

Tenant resolution is domain-based: a login carries its tenant's globally-unique `domain`,
which selects the tenant before credentials are checked. The issued access token carries
`tid`/`sub`, so every later request knows its tenant with no DB lookup.

Boundary: this service depends only on ports (`ITenantRepository`, `IUserRepository`,
`IRefreshTokenRepository`, `IPasswordHasher`, `ITokenService`, `IUnitOfWork`) — no FastAPI,
JWT, or SQLAlchemy imports. Registration and the pre-auth reads run inside `system_scope`
because no tenant context exists yet.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import structlog

from src.core.exceptions import InvalidCredentialsError, TokenError
from src.core.tenant_context import system_scope
from src.domain.entities.refresh_token import RefreshToken
from src.domain.entities.tenant import Tenant, TenantStatus
from src.domain.entities.user import User, UserStatus
from src.domain.interfaces.auth import IPasswordHasher, ITokenService, IUnitOfWork
from src.domain.interfaces.repositories import (
    IRefreshTokenRepository,
    ITenantRepository,
    IUserRepository,
)

logger = structlog.get_logger(__name__)

_MIN_PASSWORD_LEN = 8


@dataclass(slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_refresh(raw: str) -> str:
    # Refresh tokens are high-entropy random strings, so a fast one-way hash is enough
    # (unlike passwords). We only ever persist this digest, never the raw token.
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(
        self,
        tenant_repo: ITenantRepository,
        user_repo: IUserRepository,
        refresh_repo: IRefreshTokenRepository,
        password_hasher: IPasswordHasher,
        token_service: ITokenService,
        unit_of_work: IUnitOfWork,
        refresh_ttl_seconds: int,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.user_repo = user_repo
        self.refresh_repo = refresh_repo
        self.password_hasher = password_hasher
        self.token_service = token_service
        self.uow = unit_of_work
        self.refresh_ttl_seconds = refresh_ttl_seconds

    # --- Registration ------------------------------------------------------------

    def register(self, domain: str, email: str, password: str, name: str | None = None) -> AuthTokens:
        """Create a tenant AND its single user atomically; either both land or neither."""
        domain = _normalize_domain(domain)
        email = _normalize_email(email)
        if not domain:
            raise ValueError("domain is required")
        if "@" not in email:
            raise ValueError("a valid email is required")
        if len(password) < _MIN_PASSWORD_LEN:
            raise ValueError(f"password must be at least {_MIN_PASSWORD_LEN} characters")

        with system_scope():
            try:
                tenant = self.tenant_repo.create(
                    Tenant(domain=domain, name=name or domain, status=TenantStatus.ACTIVE)
                )
                user = self.user_repo.create(
                    User(
                        tenant_id=tenant.id,
                        email=email,
                        password_hash=self.password_hasher.hash(password),
                        status=UserStatus.ACTIVE,
                    )
                )
                tokens = self._issue(user)
                self.uow.commit()
                return tokens
            except Exception:
                # Any failure (domain taken, user insert, token store) rolls back BOTH the
                # tenant and the user — no orphan tenant.
                self.uow.rollback()
                raise

    # --- Login -------------------------------------------------------------------

    def login(self, domain: str, email: str, password: str) -> AuthTokens:
        """Resolve tenant by domain, verify the user, issue tokens.

        Anti-enumeration: every failure path returns the same generic
        `InvalidCredentialsError`; the specific reason is only logged server-side.
        """
        domain = _normalize_domain(domain)
        email = _normalize_email(email)

        with system_scope():
            tenant = self.tenant_repo.get_by_domain(domain)
            if tenant is None:
                self._deny("tenant_not_found", domain=domain)
            if tenant.status is not TenantStatus.ACTIVE:
                self._deny("tenant_not_active", domain=domain, status=str(tenant.status))

            user = self.user_repo.get_by_tenant_and_email(tenant.id, email)
            if user is None:
                self._deny("user_not_found", tenant_id=str(tenant.id))
            if not self.password_hasher.verify(password, user.password_hash):
                self._deny("bad_password", user_id=str(user.id))
            if user.status is not UserStatus.ACTIVE:
                self._deny("user_not_active", user_id=str(user.id), status=str(user.status))

            try:
                tokens = self._issue(user)
                self.uow.commit()
                return tokens
            except Exception:
                self.uow.rollback()
                raise

    # --- Refresh / logout --------------------------------------------------------

    def refresh(self, raw_refresh: str) -> AuthTokens:
        """Rotate a refresh token: revoke the presented one, issue a new one in its family.

        Presenting an already-revoked token is treated as theft: the whole family is
        revoked and the request is rejected.
        """
        token_hash = _hash_refresh(raw_refresh)
        with system_scope():
            try:
                record = self.refresh_repo.get_by_hash(token_hash)
                if record is None:
                    raise TokenError("Unknown refresh token")
                if record.revoked_at is not None:
                    self.refresh_repo.revoke_family(record.family_id)
                    self.uow.commit()
                    logger.warning("refresh_token_reuse", family_id=str(record.family_id))
                    raise TokenError("Refresh token reuse detected")
                if record.expires_at <= datetime.now(timezone.utc):
                    raise TokenError("Refresh token expired")

                user = self.user_repo.get(record.user_id)
                if user is None or user.status is not UserStatus.ACTIVE:
                    raise TokenError("User is no longer active")

                self.refresh_repo.revoke(record.id)
                tokens = self._issue(user, family_id=record.family_id)
                self.uow.commit()
                return tokens
            except Exception:
                self.uow.rollback()
                raise

    def logout(self, raw_refresh: str) -> None:
        """Revoke the whole family the presented refresh token belongs to (idempotent)."""
        token_hash = _hash_refresh(raw_refresh)
        with system_scope():
            record = self.refresh_repo.get_by_hash(token_hash)
            if record is not None:
                self.refresh_repo.revoke_family(record.family_id)
            self.uow.commit()

    # --- Helpers -----------------------------------------------------------------

    def _issue(self, user: User, family_id: UUID | None = None) -> AuthTokens:
        access_token, expires_in = self.token_service.issue_access_token(user.id, user.tenant_id)
        raw_refresh = secrets.token_urlsafe(48)
        self.refresh_repo.create(
            RefreshToken(
                user_id=user.id,
                tenant_id=user.tenant_id,
                token_hash=_hash_refresh(raw_refresh),
                family_id=family_id or uuid4(),
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.refresh_ttl_seconds),
            )
        )
        return AuthTokens(access_token=access_token, refresh_token=raw_refresh, expires_in=expires_in)

    def _deny(self, reason: str, **fields) -> None:
        # Distinct server-side signal, uniform client-side error (no enumeration leak).
        logger.info("login_denied", reason=reason, **fields)
        raise InvalidCredentialsError("Invalid credentials or inactive account")
