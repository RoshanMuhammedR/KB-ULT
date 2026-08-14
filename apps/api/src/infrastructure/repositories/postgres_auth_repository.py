from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.exceptions import EmailAlreadyExistsError
from src.domain.entities.refresh_token import RefreshToken
from src.domain.entities.tenant import Tenant
from src.domain.entities.user import User
from src.infrastructure.database.models import RefreshTokenModel, TenantModel, UserModel
from src.infrastructure.repositories.mappers import (
    refresh_token_to_domain,
    tenant_to_domain,
    user_to_domain,
)

# tenants/users/refresh_tokens are NOT TenantScoped: they are read/written during
# registration, login, and refresh — before (or independent of) a tenant context. The
# auth service wraps these calls in `system_scope`, so the tenant listeners stand down.
#
# Writes here only *flush* (never commit): registration must create the tenant AND its
# user atomically, so the AuthService owns the transaction and commits once at the end.


class TenantRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, tenant_id: UUID) -> Tenant | None:
        model = self.db.get(TenantModel, tenant_id)
        return tenant_to_domain(model) if model else None

    def create(self, tenant: Tenant) -> Tenant:
        # Nothing about a tenant is unique, so this cannot conflict — the uniqueness that can
        # fail registration lives on `users.email` below.
        model = TenantModel(id=tenant.id, name=tenant.name, status=str(tenant.status))
        self.db.add(model)
        self.db.flush()
        self.db.refresh(model)
        return tenant_to_domain(model)


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, user_id: UUID) -> User | None:
        model = self.db.get(UserModel, user_id)
        return user_to_domain(model) if model else None

    def get_by_email(self, email: str) -> User | None:
        # Email is globally unique, so this is the whole of login's subject resolution.
        model = self.db.scalar(select(UserModel).where(UserModel.email == email))
        return user_to_domain(model) if model else None

    def get_by_google_sub(self, google_sub: str) -> User | None:
        # `google_sub` is globally unique, so one Google account maps to exactly one user.
        model = self.db.scalar(select(UserModel).where(UserModel.google_sub == google_sub))
        return user_to_domain(model) if model else None

    def create(self, user: User) -> User:
        model = UserModel(
            id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            password_hash=user.password_hash,
            google_sub=user.google_sub,
            name=user.name,
            status=str(user.status),
            email_verified_at=user.email_verified_at,
        )
        self.db.add(model)
        try:
            self.db.flush()
        except IntegrityError as exc:  # the global-unique `uq_users_email` constraint
            raise EmailAlreadyExistsError("That email is already registered") from exc
        self.db.refresh(model)
        return user_to_domain(model)

    def link_google(self, user_id: UUID, google_sub: str) -> User:
        """Attach a Google subject to an existing (password) account.

        Only ever called after Google reported the email as verified — that check is what
        makes linking safe, since otherwise anyone able to assert an address could claim
        someone else's account.
        """
        model = self.db.get(UserModel, user_id)
        if model is None:
            raise ValueError("User not found")
        model.google_sub = google_sub
        if model.email_verified_at is None:
            model.email_verified_at = datetime.now(timezone.utc)
        self.db.flush()
        self.db.refresh(model)
        return user_to_domain(model)


class RefreshTokenRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, token: RefreshToken) -> RefreshToken:
        model = RefreshTokenModel(
            id=token.id,
            user_id=token.user_id,
            tenant_id=token.tenant_id,
            token_hash=token.token_hash,
            family_id=token.family_id,
            expires_at=token.expires_at,
            revoked_at=token.revoked_at,
        )
        self.db.add(model)
        self.db.flush()
        self.db.refresh(model)
        return refresh_token_to_domain(model)

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        model = self.db.scalar(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        return refresh_token_to_domain(model) if model else None

    def revoke(self, token_id: UUID) -> None:
        self.db.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.id == token_id)
            .values(revoked_at=datetime.now(timezone.utc))
        )

    def revoke_family(self, family_id: UUID) -> None:
        self.db.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.family_id == family_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
