"""Composition root — the single place the concrete object graph is assembled.

Both entrypoints share these builders:
  * the HTTP layer (via thin FastAPI `Depends` wrappers in http/dependencies),
  * the ingestion worker (via the Procrastinate task).

Keeping construction here means the request path and the worker path wire up the
exact same adapters, so behaviour can't drift between them. Each builder takes an
already-opened `Session` (request-scoped in HTTP, worker-scoped in the worker) plus
`Settings`, and returns a ready-to-use application service.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.application.chat.prompt_builder import PromptBuilder
from src.application.chat.service import ChatService
from src.application.ingestion.service import IngestionService
from src.application.knowledge_base import KnowledgeBaseService
from src.core.config import Settings
from src.domain.entities import SourceType
from src.domain.interfaces import IFileStorage, IJobQueue
from src.infrastructure.ai_providers import AICreditsEmbeddingProvider, AICreditsLLMProvider
from src.infrastructure.document_parsing import DoclingPDFAdapter
from src.infrastructure.langchain_adapters.chat_model import OpenAICompatibleChatAdapter
from src.infrastructure.langchain_adapters.embeddings import OpenAICompatibleEmbeddingsAdapter
from src.infrastructure.langchain_adapters.text_splitter import RecursiveSplitterAdapter
from src.infrastructure.repositories import (
    ChunkRepository,
    IngestionJobEventRepository,
    IngestionJobRepository,
    KnowledgeAssetRepository,
    KnowledgeBaseRepository,
)
from src.infrastructure.storage import FilebaseAdapter
from src.infrastructure.vector_store.pgvector import PgVectorStore
from src.ingestion.handlers import PdfSourceHandler
from src.ingestion.registry import SourceHandlerRegistry
from src.processing.chunking import RecursiveKnowledgeAssetChunker
from src.retrieval.retriever import Retriever


def build_file_storage(settings: Settings) -> IFileStorage:
    return FilebaseAdapter(settings)


def build_job_queue() -> IJobQueue:
    # Imported lazily so importing the composition root doesn't drag in Procrastinate
    # (and its DB connector) for callers that only need, say, the chat service.
    from src.infrastructure.queue import ProcrastinateJobQueue

    return ProcrastinateJobQueue()


def _build_source_handler_registry(file_storage: IFileStorage) -> SourceHandlerRegistry:
    # One handler per supported SourceType. Handlers own acquisition (download from
    # storage) too, so each gets the file storage it needs. Adding website/YouTube is
    # a new `registry.register(SourceType.X, XHandler(...))` line here — nothing else.
    registry = SourceHandlerRegistry()
    registry.register(SourceType.PDF, PdfSourceHandler(DoclingPDFAdapter(), file_storage))
    return registry


def _build_embedding_provider(settings: Settings) -> AICreditsEmbeddingProvider:
    return AICreditsEmbeddingProvider(
        adapter=OpenAICompatibleEmbeddingsAdapter(
            api_key=settings.aicredits_api_key,
            base_url=settings.aicredits_base_url,
            model=settings.aicredits_embedding_model,
        ),
        model=settings.aicredits_embedding_model,
        expected_dimensions=settings.embedding_dimensions,
    )


def build_ingestion_service(db: Session, settings: Settings) -> IngestionService:
    # Assembles the full ingestion graph: repositories (asset/chunk/job/job-event),
    # source-handler registry, chunker, embedder, vector store, object storage, and the
    # job queue. File storage is shared with the handlers so acquisition and upload use
    # the same adapter.
    file_storage = build_file_storage(settings)
    return IngestionService(
        kb_repo=KnowledgeBaseRepository(db),
        asset_repo=KnowledgeAssetRepository(db),
        chunk_repo=ChunkRepository(db),
        job_repo=IngestionJobRepository(db),
        job_event_repo=IngestionJobEventRepository(db),
        source_handler_registry=_build_source_handler_registry(file_storage),
        chunker=RecursiveKnowledgeAssetChunker(
            RecursiveSplitterAdapter(settings.chunk_size_tokens, settings.chunk_overlap_tokens)
        ),
        embedding_provider=_build_embedding_provider(settings),
        vector_store=PgVectorStore(db),
        file_storage=file_storage,
        job_queue=build_job_queue(),
    )


def build_chat_service(db: Session, settings: Settings) -> ChatService:
    llm_provider = AICreditsLLMProvider(
        OpenAICompatibleChatAdapter(
            api_key=settings.aicredits_api_key,
            base_url=settings.aicredits_base_url,
            model=settings.aicredits_chat_model,
        )
    )
    return ChatService(
        kb_repo=KnowledgeBaseRepository(db),
        embedding_provider=_build_embedding_provider(settings),
        retriever=Retriever(PgVectorStore(db)),
        llm_provider=llm_provider,
        prompt_builder=PromptBuilder(),
        top_k=settings.retrieval_top_k,
        threshold=settings.retrieval_score_threshold,
        min_context_chunks=settings.retrieval_min_context_chunks,
    )


def build_knowledge_base_service(db: Session) -> KnowledgeBaseService:
    return KnowledgeBaseService(KnowledgeBaseRepository(db))
