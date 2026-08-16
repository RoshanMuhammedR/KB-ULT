from langchain_core.documents import Document

from src.domain.entities import (
    AssetStatus,
    Chunk,
    Conversation,
    IngestionJob,
    JobEvent,
    JobStatus,
    KnowledgeAsset,
    KnowledgeBase,
    Message,
    MessageRole,
)
from src.domain.entities.refresh_token import RefreshToken
from src.domain.entities.tenant import Tenant, TenantStatus
from src.domain.entities.user import User, UserStatus
from src.infrastructure.database.models import (
    ChunkModel,
    ConversationModel,
    IngestionJobEventModel,
    IngestionJobModel,
    KnowledgeAssetModel,
    KnowledgeBaseModel,
    MessageModel,
    RefreshTokenModel,
    TenantModel,
    UserModel,
)


def tenant_to_domain(model: TenantModel) -> Tenant:
    return Tenant(
        id=model.id,
        name=model.name,
        status=TenantStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


def user_to_domain(model: UserModel) -> User:
    return User(
        id=model.id,
        tenant_id=model.tenant_id,
        email=model.email,
        password_hash=model.password_hash,
        google_sub=model.google_sub,
        name=model.name,
        status=UserStatus(model.status),
        email_verified_at=model.email_verified_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


def refresh_token_to_domain(model: RefreshTokenModel) -> RefreshToken:
    return RefreshToken(
        id=model.id,
        user_id=model.user_id,
        tenant_id=model.tenant_id,
        token_hash=model.token_hash,
        family_id=model.family_id,
        expires_at=model.expires_at,
        revoked_at=model.revoked_at,
        created_at=model.created_at,
    )


def kb_to_domain(model: KnowledgeBaseModel) -> KnowledgeBase:
    return KnowledgeBase(
        id=model.id,
        name=model.name,
        owner_id=model.owner_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def documents_to_storage(documents: list[Document]) -> list[dict]:
    """`Document` -> plain JSON for the `documents` JSONB column.

    Explicit because `sanitize_json_for_storage` only strips NUL bytes: it returns any
    object it doesn't recognise by identity, so an un-dumped `Document` would sail through
    it and only fail later, inside `json.dumps` at commit time.
    """
    return [document.model_dump() for document in documents]


def documents_to_domain(rows: list[dict] | None) -> list[Document]:
    """The inverse, applied on every read.

    Doing this here rather than in the caller is what makes the two ingestion paths agree:
    a fresh run chunks the objects the handler just built, while a retry resuming at the
    chunking step re-loads them from JSONB. Both must yield `Document`s.

    Rows written before the `documents` column existed decode to `[]`, which the pipeline
    reads as "re-extract".
    """
    documents: list[Document] = []
    for row in rows or []:
        if isinstance(row, dict) and row.get("page_content") is not None:
            documents.append(
                Document(
                    page_content=row["page_content"],
                    metadata=row.get("metadata") or {},
                )
            )
    return documents


def asset_to_domain(model: KnowledgeAssetModel) -> KnowledgeAsset:
    return KnowledgeAsset(
        id=model.id,
        knowledge_base_id=model.knowledge_base_id,
        lineage_id=model.lineage_id,
        version=model.version,
        filename=model.filename,
        title=model.title,
        source_type=model.source_type,
        storage_key=model.storage_key,
        status=AssetStatus(model.status),
        failed_step=model.failed_step,
        error_message=model.error_message,
        text_content=model.text_content,
        metadata=model.metadata_ or {},
        documents=documents_to_domain(model.documents),
        superseded_at=model.superseded_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def job_to_domain(model: IngestionJobModel) -> IngestionJob:
    return IngestionJob(
        id=model.id,
        asset_id=model.asset_id,
        job_type=model.job_type,
        status=JobStatus(model.status),
        attempts=model.attempts,
        max_attempts=model.max_attempts,
        last_error=model.last_error,
        scheduled_at=model.scheduled_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def event_to_domain(model: IngestionJobEventModel) -> JobEvent:
    return JobEvent(
        id=model.id,
        asset_id=model.asset_id,
        job_id=model.job_id,
        level=model.level,
        event=model.event,
        message=model.message,
        data=model.data_ or {},
        ts=model.ts,
    )


def chunk_to_domain(model: ChunkModel) -> Chunk:
    return Chunk(
        id=model.id,
        knowledge_asset_id=model.knowledge_asset_id,
        chunk_index=model.chunk_index,
        text=model.text,
        metadata=model.metadata_ or {},
        created_at=model.created_at,
    )


def message_to_domain(model: MessageModel) -> Message:
    return Message(
        id=model.id,
        conversation_id=model.conversation_id,
        role=MessageRole(model.role),
        content=model.content,
        citations=model.citations or [],
        insufficient_context=model.insufficient_context,
        created_at=model.created_at,
    )


def conversation_to_domain(
    model: ConversationModel, messages: list[MessageModel] | None = None
) -> Conversation:
    """`messages` is passed explicitly so list views can skip loading the whole thread."""
    return Conversation(
        id=model.id,
        knowledge_base_id=model.knowledge_base_id,
        title=model.title,
        messages=[message_to_domain(message) for message in messages or []],
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
