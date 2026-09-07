from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base
from src.infrastructure.database.tenancy import TenantScoped


class TenantModel(Base):
    """A tenant — the top-level isolation boundary, i.e. a workspace. It carries no
    externally-addressable identifier: a tenant is reached only through one of its users.
    Not itself `TenantScoped`: it is the root of the tenant chain and is read pre-auth
    (during login) under `system_scope`.
    """

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # A display label only — deliberately not unique.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # active | suspended | deleted (stored as a string, like the existing AssetStatus).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = mapped_column(DateTime(timezone=True), nullable=True)


class UserModel(Base):
    """A tenant's user, and the subject of every credential.

    `email` is unique **globally** (`uq_users_email`), which is what lets a login present an
    email alone and resolve both the user and their tenant. Registration creates exactly one
    owner per tenant, but nothing in the schema forbids more — adding teammates later needs
    no migration on the domain tables.

    Not `TenantScoped`: read pre-auth (login) under `system_scope`.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("google_sub", name="uq_users_google_sub"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Stored lowercased; compared case-insensitively at the app layer (no citext).
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # NULL for accounts created through Google, which have no password at all.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Google's stable subject id, set when an account is created through or linked to Google.
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # active | suspended | deleted | invited.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # Unused today (registration activates immediately); present so an email-verification
    # flow can be added without a schema change.
    email_verified_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshTokenModel(Base):
    """Durable, revocable refresh-token record (rotation-based revocation — see plan §4).

    Kept in Postgres, not Valkey: revocation truth must survive cache eviction. Only the
    token's hash is stored. Reuse of a revoked token revokes the whole `family_id`.
    Not `TenantScoped`: issued/rotated during auth, under `system_scope`.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    expires_at = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeBaseModel(TenantScoped, Base):
    __tablename__ = "knowledge_bases"
    # One knowledge base per (tenant, name). `ensure_default` is a read-then-insert that two
    # concurrent first requests could both win; this is what makes its ON CONFLICT clause
    # legal and the duplicate impossible. See migration 0008.
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_knowledge_base_tenant_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    assets: Mapped[list[KnowledgeAssetModel]] = relationship(back_populates="knowledge_base")


class KnowledgeAssetModel(TenantScoped, Base):
    __tablename__ = "knowledge_assets"
    __table_args__ = (UniqueConstraint("lineage_id", "version", name="uq_asset_lineage_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), nullable=False)
    lineage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    failed_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    # The parsed source as serialized LangChain `Document`s — the handoff between parsing
    # and chunking. Its own column rather than a key in `metadata` because `metadata` is
    # returned verbatim to the client by KnowledgeAssetSchema, and this holds the entire
    # text of the source: shipping it on every status poll was pure waste. A retry that
    # resumes at the chunking step reads these back instead of re-parsing.
    documents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    superseded_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    knowledge_base: Mapped[KnowledgeBaseModel] = relationship(back_populates="assets")
    chunks: Mapped[list[ChunkModel]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class IngestionJobModel(TenantScoped, Base):
    """Domain-owned ingestion job record (see IngestionJob entity).

    Separate from Procrastinate's internal tables: this is the job history the app
    and frontend query, so it stays stable if the queue engine is ever swapped.
    """

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        # Fast lookup of "the latest job for this asset" and worker/status scans.
        Index("ix_ingestion_jobs_asset_id", "asset_id"),
        Index("ix_ingestion_jobs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, default="ingest_asset")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at = mapped_column(DateTime(timezone=True), nullable=True)
    started_at = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class IngestionJobEventModel(TenantScoped, Base):
    """Durable worker log: one row per pipeline transition / terminal state.

    structlog output is stdout-only; this is the queryable trail the `/jobs` dashboard
    reads. Written explicitly by the ingestion service, not scraped from the logger.
    `job_id` is nullable (an event may outlive its job); `asset_id` is always set.
    """

    __tablename__ = "ingestion_job_events"
    __table_args__ = (
        # Dashboard reads the trail per asset, ordered by time.
        Index("ix_ingestion_job_events_asset_id", "asset_id"),
        Index("ix_ingestion_job_events_job_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=True
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_: Mapped[dict] = mapped_column("data", JSONB, nullable=False, default=dict)
    ts = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ChunkModel(TenantScoped, Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("knowledge_asset_id", "chunk_index", name="uq_chunk_asset_index"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    # Small-to-big retrieval: children are embedded and searched, the parent section is what
    # reaches the prompt. Self-referential, and CASCADE because `replace_for_asset` deletes a
    # whole asset's chunks in one statement without ordering parents last.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # What is vectorised: `text` plus a one-line description of its section. Kept separate so
    # `text` stays exactly what is displayed and cited, and so `fts` — a generated column over
    # `text` — keeps matching the document's own words rather than our prose about it.
    embed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # See ChunkModality. A column rather than a metadata key so the per-modality relevance
    # floor is a SQL filter instead of a JSONB lookup.
    modality: Mapped[str] = mapped_column(String(16), nullable=False, server_default="text")
    # Lexical search vector, maintained by Postgres itself (see 0006). `Computed` tells
    # SQLAlchemy to leave it out of INSERTs and UPDATEs, so ingestion never touches it —
    # the column simply follows `text`.
    fts = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', text)", persisted=True),
        nullable=True,
    )
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset: Mapped[KnowledgeAssetModel] = relationship(back_populates="chunks")
    embeddings: Mapped[list[EmbeddingModel]] = relationship(back_populates="chunk", cascade="all, delete-orphan")


class EmbeddingModel(TenantScoped, Base):
    __tablename__ = "embeddings"
    __table_args__ = (UniqueConstraint("chunk_id", "model", name="uq_embedding_chunk_model"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector = mapped_column(Vector(1536), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    chunk: Mapped[ChunkModel] = relationship(back_populates="embeddings")


class ConversationModel(TenantScoped, Base):
    """A persisted chat thread.

    Scoped to a knowledge base rather than free-floating, so a future second library
    inherits the right threads without a data migration.
    """

    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_updated_at", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    messages: Mapped[list[MessageModel]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageModel.created_at",
    )


class MessageModel(TenantScoped, Base):
    """One turn in a thread.

    `citations` stores the citation dicts verbatim so a thread re-reads correctly years
    later, and so "which answers cited this source?" is a GIN containment query rather than
    a re-run of retrieval.
    """

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index(
            "ix_messages_citations",
            "citations",
            postgresql_using="gin",
            postgresql_ops={"citations": "jsonb_path_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    # user | assistant (stored as a string, like the existing status columns).
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # How the answer was reached: the loop's hop-by-hop record. Nullable because answers
    # written before 0010 genuinely have none, and because only the assistant turn has one.
    trace: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Whether the answer's citations held up. Written *after* the row is inserted on the
    # streaming path, because the check runs after `done` to protect time-to-first-token.
    grounding: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    insufficient_context: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation: Mapped[ConversationModel] = relationship(back_populates="messages")


class ChunkSignalModel(TenantScoped, Base):
    """What a passage has actually done for this workspace, accumulated across answers.

    Rows are created and incremented by a Core `insert().on_conflict_do_update()` — the one
    write path in this codebase that does not go through the ORM, and therefore the one that
    must set `tenant_id` by hand. See `postgres_chunk_signal_repository.record`.

    `user_id` is stamped because `TenantScoped` stamps it, and is deliberately never filtered
    on: whether a passage answers a question well is a property of the corpus, not of whoever
    happened to ask. Reading it as attribution would turn a shared signal into a per-person
    filter bubble.
    """

    __tablename__ = "chunk_signals"
    __table_args__ = (
        # The ON CONFLICT target. `tenant_id` is part of it so a wrong hand-written tenant
        # cannot merge two workspaces' counters — it would collide with nothing and insert.
        UniqueConstraint("tenant_id", "chunk_id", name="uq_chunk_signal_tenant_chunk"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    # Recorded, but never fed into the prior: being retrieved and cited is exactly what the
    # prior influences, so letting it feed back would close the loop with no outside signal.
    cited: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unsupported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    upvoted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    downvoted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_cited_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MessageFeedbackModel(TenantScoped, Base):
    """One reader's verdict on one answer.

    `rating` is a signed SmallInteger rather than the `String(16)` used for every other state
    column here. Deliberate: it is summed into a weighted score rather than compared against a
    name, and storing "up"/"down" would mean mapping strings to numbers on every read. The
    CHECK keeps the set as closed as an enum would.
    """

    __tablename__ = "message_feedback"
    __table_args__ = (
        CheckConstraint("rating IN (-1, 1)", name="ck_message_feedback_rating"),
        # One verdict per person per answer. Two people disagreeing is a fact to record.
        UniqueConstraint("message_id", "user_id", name="uq_message_feedback_message_user"),
        Index("ix_message_feedback_message_id", "message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
