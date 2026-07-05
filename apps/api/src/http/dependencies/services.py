from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.chat.prompt_builder import PromptBuilder
from src.application.chat.service import ChatService
from src.application.ingestion.service import IngestionService
from src.application.knowledge_base import KnowledgeBaseService
from src.core.config import Settings, get_settings
from src.domain.interfaces import IFileStorage
from src.infrastructure.repositories import ChunkRepository, KnowledgeAssetRepository, KnowledgeBaseRepository
from src.infrastructure.database.session import get_db
from src.infrastructure.document_parsing import DoclingPDFAdapter
from src.infrastructure.langchain_adapters.chat_model import OpenAICompatibleChatAdapter
from src.infrastructure.langchain_adapters.embeddings import OpenAICompatibleEmbeddingsAdapter
from src.infrastructure.langchain_adapters.text_splitter import RecursiveSplitterAdapter
from src.infrastructure.ai_providers import AICreditsEmbeddingProvider, AICreditsLLMProvider
from src.infrastructure.storage import FilebaseAdapter
from src.infrastructure.vector_store.pgvector import PgVectorStore
from src.processing.chunking import RecursiveKnowledgeAssetChunker
from src.ingestion.parsers import PDFParser
from src.ingestion.registry import ParserRegistry
from src.retrieval.retriever import Retriever

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_ingestion_service(db: DbSession, settings: AppSettings) -> IngestionService:
    embedding_adapter = OpenAICompatibleEmbeddingsAdapter(
        api_key=settings.aicredits_api_key,
        base_url=settings.aicredits_base_url,
        model=settings.aicredits_embedding_model,
    )
    embedding_provider = AICreditsEmbeddingProvider(
        adapter=embedding_adapter,
        model=settings.aicredits_embedding_model,
        expected_dimensions=settings.embedding_dimensions,
    )
    parser_registry = ParserRegistry()
    parser_registry.register(".pdf", PDFParser(DoclingPDFAdapter()))
    return IngestionService(
        kb_repo=KnowledgeBaseRepository(db),
        asset_repo=KnowledgeAssetRepository(db),
        chunk_repo=ChunkRepository(db),
        parser_registry=parser_registry,
        chunker=RecursiveKnowledgeAssetChunker(
            RecursiveSplitterAdapter(settings.chunk_size_tokens, settings.chunk_overlap_tokens)
        ),
        embedding_provider=embedding_provider,
        vector_store=PgVectorStore(db),
        file_storage=get_file_storage(settings),
    )


def get_file_storage(settings: AppSettings) -> IFileStorage:
    return FilebaseAdapter(settings)


def get_knowledge_base_service(db: DbSession) -> KnowledgeBaseService:
    return KnowledgeBaseService(KnowledgeBaseRepository(db))


def get_chat_service(db: DbSession, settings: AppSettings) -> ChatService:
    embedding_provider = AICreditsEmbeddingProvider(
        adapter=OpenAICompatibleEmbeddingsAdapter(
            api_key=settings.aicredits_api_key,
            base_url=settings.aicredits_base_url,
            model=settings.aicredits_embedding_model,
        ),
        model=settings.aicredits_embedding_model,
        expected_dimensions=settings.embedding_dimensions,
    )
    llm_provider = AICreditsLLMProvider(
        OpenAICompatibleChatAdapter(
            api_key=settings.aicredits_api_key,
            base_url=settings.aicredits_base_url,
            model=settings.aicredits_chat_model,
        )
    )
    return ChatService(
        kb_repo=KnowledgeBaseRepository(db),
        embedding_provider=embedding_provider,
        retriever=Retriever(PgVectorStore(db)),
        llm_provider=llm_provider,
        prompt_builder=PromptBuilder(),
        top_k=settings.retrieval_top_k,
        threshold=settings.retrieval_score_threshold,
        min_context_chunks=settings.retrieval_min_context_chunks,
    )
