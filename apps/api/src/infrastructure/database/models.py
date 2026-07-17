from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base


class KnowledgeBaseModel(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    assets: Mapped[list[KnowledgeAssetModel]] = relationship(back_populates="knowledge_base")


class KnowledgeAssetModel(Base):
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
    superseded_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    knowledge_base: Mapped[KnowledgeBaseModel] = relationship(back_populates="assets")
    chunks: Mapped[list[ChunkModel]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class IngestionJobModel(Base):
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


class IngestionJobEventModel(Base):
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


class ChunkModel(Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("knowledge_asset_id", "chunk_index", name="uq_chunk_asset_index"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset: Mapped[KnowledgeAssetModel] = relationship(back_populates="chunks")
    embeddings: Mapped[list[EmbeddingModel]] = relationship(back_populates="chunk", cascade="all, delete-orphan")


class EmbeddingModel(Base):
    __tablename__ = "embeddings"
    __table_args__ = (UniqueConstraint("chunk_id", "model", name="uq_embedding_chunk_model"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector = mapped_column(Vector(1536), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    chunk: Mapped[ChunkModel] = relationship(back_populates="embeddings")
