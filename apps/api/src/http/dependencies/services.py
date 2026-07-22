from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.application.auth import AuthService
from src.application.chat.service import ChatService
from src.application.ingestion.service import IngestionService
from src.application.knowledge_base import KnowledgeBaseService
from src.composition import (
    build_auth_service,
    build_cache,
    build_chat_service,
    build_file_storage,
    build_ingestion_service,
    build_knowledge_base_service,
    build_token_service,
)
from src.core.config import Settings, get_settings
from src.core.exceptions import TokenError
from src.core.identity import Identity
from src.domain.interfaces import IFileStorage
from src.domain.interfaces.cache import ICache
from src.infrastructure.database.session import get_db

# These are intentionally thin: they only bind FastAPI's request-scoped `db` and the
# cached `Settings` to the shared builders in src/composition.py. The worker uses the
# same builders with a worker-scoped session, so both paths wire up identically.

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_auth_service(db: DbSession, settings: AppSettings) -> AuthService:
    return build_auth_service(db, settings)


def get_ingestion_service(db: DbSession, settings: AppSettings) -> IngestionService:
    return build_ingestion_service(db, settings)


def get_file_storage(settings: AppSettings) -> IFileStorage:
    return build_file_storage(settings)


def get_cache(settings: AppSettings) -> ICache:
    return build_cache(settings)


def get_knowledge_base_service(db: DbSession) -> KnowledgeBaseService:
    return build_knowledge_base_service(db)


def get_chat_service(db: DbSession, settings: AppSettings) -> ChatService:
    return build_chat_service(db, settings)


def get_current_identity(request: Request, settings: AppSettings) -> Identity:
    """Decode the bearer access token at the route level.

    The `/auth/*` prefix is exempt from `AuthenticationMiddleware` (it must serve
    login/register pre-auth), so the few authenticated auth endpoints (`/auth/me`,
    `/auth/handoff/issue`) resolve the caller here instead of reading `scope["kb.identity"]`.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    token = header[7:].strip()
    try:
        claims = build_token_service(settings).decode_access_token(token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return Identity(tenant_id=claims.tenant_id, user_id=claims.user_id)
