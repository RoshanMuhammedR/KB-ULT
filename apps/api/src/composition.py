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

from sqlalchemy.ext.asyncio import AsyncSession

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
from src.infrastructure.cache import EmbeddingCache, RedisCache
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
from src.infrastructure.repositories.unit_of_work import SessionAtomicScope
from src.infrastructure.storage import FilebaseAdapter
from src.infrastructure.vector_store.pgvector import PgVectorStore
from src.ingestion.handlers import (
    AudioSourceHandler,
    MarkdownSourceHandler,
    PdfSourceHandler,
    PptxSourceHandler,
    YouTubeSourceHandler,
    build_transcript_fetcher,
)
from src.ingestion.registry import SourceHandlerRegistry
from src.application.chat.agentic import (
    AgenticChatService,
    ContextAssembler,
    GroundingChecker,
    RetrievalLoop,
)
from src.processing.chunking import StructureAwareChunker
from src.retrieval.langchain.query import QueryResolver, QueryRewriter, SufficiencyChecker
from src.retrieval.langchain.rerank import ScoringReranker
from src.retrieval.retriever import Retriever


def build_file_storage(settings: Settings) -> IFileStorage:
    return FilebaseAdapter(settings)


# One cache client (and its connection pool) is shared process-wide; tenant isolation is
# in the KEYS (see infrastructure/cache/keys.py), not in separate client instances.
_cache: RedisCache | None = None


def build_cache(settings: Settings) -> ICache:
    global _cache
    if _cache is None:
        _cache = RedisCache(settings.cache_url)
    return _cache


def build_job_queue(db: AsyncAsyncSession | None = None) -> IJobQueue:
    # Imported lazily so importing the composition root doesn't drag in Procrastinate
    # (and its DB connector) for callers that only need, say, the chat service.
    from src.infrastructure.queue import ProcrastinateJobQueue, TransactionalProcrastinateJobQueue

    # Given a Session, enqueue through it: the queue table is in the same database, so the
    # job row commits with the asset row it belongs to instead of on its own connection.
    # Without one (nothing does this today, but the port allows it), fall back to the
    # connector-owned defer, which is correct but not atomic with the caller's writes.
    if db is not None:
        return TransactionalProcrastinateJobQueue(db)
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
    registry.register(SourceType.YOUTUBE, YouTubeSourceHandler(build_transcript_fetcher()))
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


def _build_chat_adapter(settings: Settings, model: str) -> OpenAICompatibleChatAdapter:
    """One chat adapter for a named model. `.client` is the raw LangChain model, which is
    what the pipeline's structured-output steps need; the wrapper is what the domain uses."""
    return OpenAICompatibleChatAdapter(
        api_key=settings.aicredits_api_key,
        base_url=settings.aicredits_base_url,
        model=model,
    )


def _build_fast_llm(settings: Settings) -> AICreditsLLMProvider:
    """The small model used for the pipeline's mechanical steps.

    Query resolution, relevance grading, reranking, sufficiency, grounding and the
    per-section blurb all run several times per question and are judged on latency rather
    than prose quality. Keeping them on a separate setting means the answering model can be
    upgraded without multiplying the cost of everything around it.
    """
    return AICreditsLLMProvider(
        OpenAICompatibleChatAdapter(
            api_key=settings.aicredits_api_key,
            base_url=settings.aicredits_base_url,
            model=settings.aicredits_fast_model,
        )
    )


def build_ingestion_service(db: AsyncSession, settings: Settings) -> IngestionService:
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
        chunker=StructureAwareChunker(
            RecursiveSplitterAdapter(settings.chunk_size_tokens, settings.chunk_overlap_tokens),
            # The describing model, not the answering one: a one-sentence blurb per section
            # is exactly the work a small model does well and a large one overcharges for.
            llm_provider=_build_fast_llm(settings),
            enrich=settings.enrich_chunks,
        ),
        embedding_provider=_build_embedding_provider(settings),
        vector_store=PgVectorStore(db),
        file_storage=file_storage,
        job_queue=build_job_queue(db),
        atomic_scope=SessionAtomicScope(db),
        max_audio_upload_bytes=settings.max_audio_upload_bytes,
    )


def build_chat_service(db: AsyncSession, settings: Settings) -> ChatService:
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
        retriever=Retriever(
            PgVectorStore(db),
            candidate_multiplier=settings.retrieval_candidate_multiplier,
            rrf_k=settings.retrieval_rrf_k,
        ),
        llm_provider=llm_provider,
        prompt_builder=PromptBuilder(),
        top_k=settings.retrieval_top_k,
        threshold=settings.retrieval_score_threshold,
        min_context_chunks=settings.retrieval_min_context_chunks,
        conversation_repo=ConversationRepository(db),
    )


def build_agentic_chat_service(db: AsyncSession, settings: Settings) -> AgenticChatService:
    """Assemble the agentic query pipeline.

    Two models, deliberately: the answering model writes the prose a user reads, and the
    fast model does everything else — resolving the query, scoring candidates, judging
    sufficiency, checking grounding. Those run several times per question and are judged on
    latency, so paying answer-model prices for them would multiply the cost of a question
    without improving a word of the output.
    """
    answering = _build_chat_adapter(settings, settings.aicredits_chat_model).client
    fast = _build_chat_adapter(settings, settings.aicredits_fast_model).client

    vector_store = PgVectorStore(db)
    chunk_repo = ChunkRepository(db)

    return AgenticChatService(
        kb_repo=KnowledgeBaseRepository(db),
        conversation_repo=ConversationRepository(db),
        chunk_repo=chunk_repo,
        loop=RetrievalLoop(
            vector_store=vector_store,
            # Query embeddings go through the cache: a repeated question is common in a
            # personal knowledge base, and the vector for a given string never changes.
            embedding_provider=EmbeddingCache(
                _build_embedding_provider(settings),
                build_cache(settings),
                model=settings.aicredits_embedding_model,
                ttl_seconds=settings.embedding_cache_ttl_seconds,
            ),
            reranker=ScoringReranker(
                fast,
                top_n=settings.rerank_top_n,
                threshold=settings.rerank_relevance_threshold,
                asr_threshold=settings.rerank_asr_relevance_threshold,
                timeout_seconds=settings.rerank_timeout_seconds,
            ),
            rewriter=QueryRewriter(fast),
            sufficiency=SufficiencyChecker(fast, min_chunks=settings.retrieval_min_context_chunks),
            max_hops=settings.max_retrieval_hops,
            # Both arms over-fetch so fusion has something to promote and the reranker has
            # a pool to judge rather than an already-truncated list.
            candidate_limit=settings.retrieval_top_k * settings.retrieval_candidate_multiplier,
            threshold=settings.retrieval_score_threshold,
            rrf_k=settings.retrieval_rrf_k,
        ),
        resolver=QueryResolver(fast),
        assembler=ContextAssembler(chunk_repo, token_budget=settings.context_token_budget),
        grounding=GroundingChecker(fast),
        llm_provider=AICreditsLLMProvider(_build_chat_adapter(settings, settings.aicredits_chat_model)),
        grounding_blocking=settings.grounding_blocking,
    )


def build_knowledge_base_service(db: AsyncSession) -> KnowledgeBaseService:
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


def build_auth_service(db: AsyncSession, settings: Settings) -> AuthService:
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
