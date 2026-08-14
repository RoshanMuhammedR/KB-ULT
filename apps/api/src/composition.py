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

from src.application.auth import AuthService
from src.application.chat.prompt_builder import PromptBuilder
from src.application.chat.service import ChatService
from src.application.ingestion.service import IngestionService
from src.application.knowledge_base import KnowledgeBaseService
from src.core.config import Settings
from src.domain.entities import SourceType
from src.domain.interfaces import IFileStorage, IJobQueue
from src.domain.interfaces.auth import ITokenService
from src.domain.interfaces.cache import ICache
from src.http.middleware import BearerTokenAuthenticator
from src.infrastructure.ai_providers import (
    AICreditsEmbeddingProvider,
    AICreditsLLMProvider,
    VoxtralTranscriptionProvider,
)
from src.infrastructure.auth import (
    Argon2PasswordHasher,
    GoogleIdTokenVerifier,
    JwtTokenService,
)
from src.infrastructure.cache import ValkeyCache
from src.infrastructure.document_parsing import PyMuPDF4LLMAdapter
from src.infrastructure.langchain_adapters.chat_model import OpenAICompatibleChatAdapter
from src.infrastructure.langchain_adapters.embeddings import OpenAICompatibleEmbeddingsAdapter
from src.infrastructure.langchain_adapters.text_splitter import RecursiveSplitterAdapter
from src.infrastructure.repositories import (
    ChunkRepository,
    ConversationRepository,
    IngestionJobEventRepository,
    IngestionJobRepository,
    KnowledgeAssetRepository,
    KnowledgeBaseRepository,
    RefreshTokenRepository,
    TenantRepository,
    UserRepository,
)
from src.infrastructure.storage import FilebaseAdapter
from src.infrastructure.vector_store.pgvector import PgVectorStore
from src.ingestion.handlers import (
    AudioSourceHandler,
    MarkdownSourceHandler,
    PdfSourceHandler,
    PptxSourceHandler,
    YouTubeSourceHandler,
)
from src.ingestion.registry import SourceHandlerRegistry
from src.processing.chunking import RecursiveKnowledgeAssetChunker
from src.retrieval.retriever import Retriever


def build_file_storage(settings: Settings) -> IFileStorage:
    return FilebaseAdapter(settings)


# One cache client (and its connection pool) is shared process-wide; tenant isolation is
# in the KEYS (see infrastructure/cache/keys.py), not in separate client instances.
_cache: ValkeyCache | None = None


def build_cache(settings: Settings) -> ICache:
    global _cache
    if _cache is None:
        _cache = ValkeyCache(settings.cache_url)
    return _cache


def build_job_queue() -> IJobQueue:
    # Imported lazily so importing the composition root doesn't drag in Procrastinate
    # (and its DB connector) for callers that only need, say, the chat service.
    from src.infrastructure.queue import ProcrastinateJobQueue

    return ProcrastinateJobQueue()


def _build_pdf_parser() -> PyMuPDF4LLMAdapter:
    # No singleton/lock needed here (unlike the old Docling adapter): PyMuPDF4LLMAdapter has
    # no model weights or expensive per-instance state to cache, so a fresh instance per call
    # is just as cheap.
    return PyMuPDF4LLMAdapter()


def _build_transcription_provider(settings: Settings) -> VoxtralTranscriptionProvider:
    return VoxtralTranscriptionProvider(
        api_key=settings.aicredits_api_key,
        base_url=settings.aicredits_base_url,
        model=settings.aicredits_transcription_model,
    )


def _build_source_handler_registry(
    file_storage: IFileStorage, settings: Settings
) -> SourceHandlerRegistry:
    # One handler per supported SourceType. Handlers own acquisition (download from
    # storage) too, so each gets the file storage it needs. Adding a website source is
    # a new `registry.register(SourceType.X, XHandler(...))` line here — nothing else.
    registry = SourceHandlerRegistry()
    registry.register(SourceType.PDF, PdfSourceHandler(_build_pdf_parser(), file_storage))
    # YouTube fetches its own content (transcript API + oEmbed), so it needs no storage.
    registry.register(SourceType.YOUTUBE, YouTubeSourceHandler())
    registry.register(SourceType.MARKDOWN, MarkdownSourceHandler(file_storage))
    registry.register(SourceType.PPTX, PptxSourceHandler(file_storage))
    registry.register(
        SourceType.AUDIO,
        AudioSourceHandler(file_storage, _build_transcription_provider(settings)),
    )
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
        source_handler_registry=_build_source_handler_registry(file_storage, settings),
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
        conversation_repo=ConversationRepository(db),
    )


def build_knowledge_base_service(db: Session) -> KnowledgeBaseService:
    return KnowledgeBaseService(KnowledgeBaseRepository(db))


def build_token_service(settings: Settings) -> ITokenService:
    # Shared by the auth service (issuing) and the HTTP middleware (decoding), so both
    # sign/verify with the same secret + algorithm.
    return JwtTokenService(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        access_ttl_seconds=settings.access_token_ttl_seconds,
    )


def build_authenticators(settings: Settings) -> list:
    # The credential-recognition chain the AuthenticationMiddleware runs in order. Bearer
    # tokens are the only mechanism today; API keys or OAuth would be appended here without
    # the tenant layer changing. No credential means a 401 — there is no fallback identity.
    return [BearerTokenAuthenticator(build_token_service(settings))]


# One verifier process-wide so the Google JWKS cache inside it is actually reused; a
# per-request instance would refetch Google's keys on every sign-in.
_google_verifier: GoogleIdTokenVerifier | None = None


def build_google_verifier(settings: Settings) -> GoogleIdTokenVerifier:
    global _google_verifier
    if _google_verifier is None or _google_verifier.client_id != settings.google_client_id:
        _google_verifier = GoogleIdTokenVerifier(settings.google_client_id)
    return _google_verifier


def build_auth_service(db: Session, settings: Settings) -> AuthService:
    # The request/worker Session doubles as the IUnitOfWork so registration's tenant+user
    # inserts commit atomically.
    return AuthService(
        tenant_repo=TenantRepository(db),
        user_repo=UserRepository(db),
        refresh_repo=RefreshTokenRepository(db),
        password_hasher=Argon2PasswordHasher(),
        token_service=build_token_service(settings),
        unit_of_work=db,
        refresh_ttl_seconds=settings.refresh_token_ttl_seconds,
        google_verifier=build_google_verifier(settings),
    )
