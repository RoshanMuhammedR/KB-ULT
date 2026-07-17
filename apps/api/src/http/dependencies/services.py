from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.chat.service import ChatService
from src.application.ingestion.service import IngestionService
from src.application.knowledge_base import KnowledgeBaseService
from src.composition import (
    build_chat_service,
    build_file_storage,
    build_ingestion_service,
    build_knowledge_base_service,
)
from src.core.config import Settings, get_settings
from src.domain.interfaces import IFileStorage
from src.infrastructure.database.session import get_db

# These are intentionally thin: they only bind FastAPI's request-scoped `db` and the
# cached `Settings` to the shared builders in src/composition.py. The worker uses the
# same builders with a worker-scoped session, so both paths wire up identically.

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_ingestion_service(db: DbSession, settings: AppSettings) -> IngestionService:
    return build_ingestion_service(db, settings)


def get_file_storage(settings: AppSettings) -> IFileStorage:
    return build_file_storage(settings)


def get_knowledge_base_service(db: DbSession) -> KnowledgeBaseService:
    return build_knowledge_base_service(db)


def get_chat_service(db: DbSession, settings: AppSettings) -> ChatService:
    return build_chat_service(db, settings)
