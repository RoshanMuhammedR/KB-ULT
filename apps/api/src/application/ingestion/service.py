from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import structlog

from src.domain.entities import AssetStatus, KnowledgeAsset
from src.domain.interfaces import (
    Chunker,
    EmbeddingProvider,
    IChunkRepository,
    IDocumentRepository,
    IFileStorage,
    IKnowledgeBaseRepository,
    VectorStore,
)
from src.domain.interfaces import IParser
from src.ingestion.sources.file_source import FileSource
from src.ingestion.registry import ParserRegistry

logger = structlog.get_logger(__name__)


class IngestionService:
    def __init__(
        self,
        kb_repo: IKnowledgeBaseRepository,
        asset_repo: IDocumentRepository,
        chunk_repo: IChunkRepository,
        parser_registry: ParserRegistry,
        chunker: Chunker,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        file_storage: IFileStorage,
    ) -> None:
        self.kb_repo = kb_repo
        self.asset_repo = asset_repo
        self.chunk_repo = chunk_repo
        self.parser_registry = parser_registry
        self.chunker = chunker
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.file_storage = file_storage

    def ingest_file(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
        user_id: str = "anonymous",
    ) -> KnowledgeAsset:
        knowledge_base = self.kb_repo.ensure_default()
        previous = self.asset_repo.latest_for_filename(knowledge_base.id, filename)
        lineage_id = previous.lineage_id if previous else uuid4()
        version = previous.version + 1 if previous else 1
        parser = self.parser_registry.get(filename)
        source_type = filename.rsplit(".", maxsplit=1)[-1].lower() if "." in filename else "unknown"
        asset_id = uuid4()
        safe_filename = self._sanitize_filename(filename)
        storage_key = f"{user_id}/{asset_id}/{safe_filename}"
        stored_key = self.file_storage.upload(
            key=storage_key,
            file_data=file_data,
            content_type=content_type or "application/octet-stream",
        )

        asset = self.asset_repo.create_pending(
            KnowledgeAsset(
                id=asset_id,
                knowledge_base_id=knowledge_base.id,
                lineage_id=lineage_id,
                version=version,
                filename=safe_filename,
                title=safe_filename,
                source_type=source_type,
                storage_key=stored_key,
                status=AssetStatus.PENDING,
                metadata={
                    "filename": safe_filename,
                    "source_type": source_type,
                    "content_type": content_type,
                },
            )
        )
        return self._run_pipeline(asset, file_data, content_type, parser)

    def retry(self, asset_id) -> KnowledgeAsset:
        asset = self.asset_repo.get(asset_id)
        if asset is None:
            raise ValueError(f"KnowledgeAsset not found: {asset_id}")
        if asset.status != AssetStatus.FAILED:
            return asset
        parser = self.parser_registry.get(asset.filename)
        content_type = asset.metadata.get("content_type")
        return self._run_pipeline(asset, None, content_type, parser)

    def _run_pipeline(
        self,
        asset: KnowledgeAsset,
        file_data: bytes | None,
        content_type: str | None,
        parser: IParser,
    ) -> KnowledgeAsset:
        step = "extracting"
        try:
            if asset.failed_step in (None, "extracting"):
                if file_data is None:
                    raise ValueError("Cannot retry extraction without re-uploading the source file")
                asset.status = AssetStatus.EXTRACTING
                asset.failed_step = None
                asset.error_message = None
                self.asset_repo.update_from_domain(asset)
                logger.info("ingestion_step", step=step, knowledge_asset_id=str(asset.id), status=asset.status)
                asset = parser.parse(
                    FileSource(
                        asset_id=asset.id,
                        file_data=file_data,
                        filename=asset.filename,
                        storage_key=asset.storage_key,
                        knowledge_base_id=asset.knowledge_base_id,
                        lineage_id=asset.lineage_id,
                        version=asset.version,
                        content_type=content_type,
                    )
                )
                self.asset_repo.update_from_domain(asset)

            step = "chunking"
            if asset.failed_step in (None, "chunking"):
                asset.status = AssetStatus.CHUNKING
                asset.failed_step = None
                asset.error_message = None
                self.asset_repo.update_from_domain(asset)
                logger.info("ingestion_step", step=step, knowledge_asset_id=str(asset.id), status=asset.status)
                chunks = self.chunker.chunk(asset)
                if not chunks:
                    raise ValueError("Source produced no indexable text chunks")
                chunks = self.chunk_repo.replace_for_asset(asset.id, chunks)
            else:
                chunks = self.chunk_repo.list_for_asset(asset.id)

            step = "embedding"
            asset.status = AssetStatus.EMBEDDING
            self.asset_repo.update_from_domain(asset)
            logger.info("ingestion_step", step=step, knowledge_asset_id=str(asset.id), status=asset.status, chunk_count=len(chunks))
            embeddings = self.embedding_provider.embed_texts([chunk.text for chunk in chunks])
            self.vector_store.upsert_embeddings(asset, chunks, embeddings)

            step = "persisting"
            asset.status = AssetStatus.READY
            asset.failed_step = None
            asset.error_message = None
            ready = self.asset_repo.update_from_domain(asset)
            self.asset_repo.supersede_previous_versions(asset.lineage_id, asset.id)
            logger.info("ingestion_step", step=step, knowledge_asset_id=str(asset.id), status=ready.status)
            return ready
        except Exception as exc:
            asset.status = AssetStatus.FAILED
            asset.failed_step = step
            asset.error_message = str(exc)
            failed = self.asset_repo.update_from_domain(asset)
            logger.exception("ingestion_failed", step=step, knowledge_asset_id=str(asset.id), error=str(exc))
            return failed

    def _sanitize_filename(self, filename: str) -> str:
        sanitized = Path(filename).name.strip().replace("/", "").replace("\\", "")
        if not sanitized:
            raise ValueError("Uploaded file must include a valid filename")
        return sanitized
