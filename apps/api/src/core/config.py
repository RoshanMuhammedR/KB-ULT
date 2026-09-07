from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILES = tuple(parent / ".env" for parent in reversed(Path(__file__).resolve().parents))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(*ENV_FILES, ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://kb_user:kb_password@localhost:5432/kb_new"
    # RLS backstop: the ORM sessions connect as this NON-superuser role so Postgres
    # Row-Level Security actually applies (superusers bypass RLS). Migrations and the
    # Procrastinate connector keep using `database_url` (superuser) for DDL/queue internals.
    # Empty => fall back to `database_url` (RLS dormant; the ORM tenant-filter still applies).
    app_database_url: str = ""
    # Refuse to boot when the ORM role bypasses RLS. A dormant backstop is invisible —
    # every query still returns the right rows because the ORM filter covers it — so the
    # only way a misconfigured APP_DATABASE_URL gets noticed is a startup check. False by
    # default so local dev boots before `scripts/create_app_role.sql` has been run; set
    # REQUIRE_RLS=1 in every deployed environment.
    require_rls: bool = False
    # Connection pool. SQLAlchemy's defaults (5 + 10 overflow = 15) are the real
    # concurrency ceiling of this service, not the 40-thread anyio pool that sync routes
    # run in: 40 concurrent requests contend for 15 connections and the 16th waits
    # `pool_timeout` seconds before raising. Size the budget as
    #   postgres max_connections  ÷  (api replicas + worker replicas × worker concurrency)
    # and leave headroom for migrations, psql, and the Procrastinate connector — which
    # keeps its own pool on `database_url` and is NOT counted here.
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    aicredits_api_key: str = ""
    aicredits_base_url: str = "https://api.aicredits.in/v1"
    aicredits_chat_model: str = "openai/gpt-4o-mini"
    aicredits_embedding_model: str = "text-embedding-3-small"
    # Hosted speech-to-text for audio sources. Nothing runs locally — no ML runtime, no
    # weights in the image — so this is just another model id on the same gateway.
    #
    # NOTE: the gateway's /audio/transcriptions route serves a much SMALLER model set than
    # /v1/models advertises — that catalog is the chat catalog. `mistralai/voxtral-small-24b-2507`
    # is listed there and works for chat, but the transcription route rejects it with
    # `400 Model ... does not exist`, which is what every audio upload used to fail on.
    # Verify a replacement against /audio/transcriptions itself, not against /v1/models.
    aicredits_transcription_model: str = "openai/whisper-1"
    # The small model that does the pipeline's mechanical thinking: query resolution,
    # relevance grading, reranking, sufficiency, grounding, and the per-section blurb at
    # ingestion. Separated from the answering model because these run several times per
    # question and are judged on latency, not prose. Point it at something cheap and fast.
    aicredits_fast_model: str = "openai/gpt-4o-mini"
    embedding_dimensions: int = 1536

    # Ceiling for the multipart upload path, enforced on Content-Length before the body is
    # read (see http/middleware/upload_limit.py). The handler reads the whole file into
    # memory against a 512 MB container, so without this one large upload is one OOM. The
    # direct-to-storage path (/documents/upload-url) does not go through the API at all and
    # is not bound by this.
    max_upload_bytes: int = 200 * 1024 * 1024

    # Audio is transcribed by a paid hosted model, so it gets a size cap the other source
    # types don't need — tighter than the ceiling above, and about money rather than memory.
    # Enforced at upload with a plain-language 400.
    max_audio_upload_bytes: int = 100 * 1024 * 1024

    # 300-600 tokens is the band where a chunk is small enough to match precisely and still
    # readable on its own. It used to be 800, chosen when a chunk had to serve as both the
    # retrieval unit and the generation unit; parent expansion means it no longer does.
    chunk_size_tokens: int = 450
    chunk_overlap_tokens: int = 70
    # One model call per section at ingestion, to describe it for embedding. Off means
    # chunks embed as themselves, which is the pre-enrichment behaviour.
    enrich_chunks: bool = True

    # --- Agentic retrieval ---
    # Two hops, not three. A question that survives two well-formed hybrid retrievals is
    # usually a question the corpus cannot answer, and a third hop buys latency and a more
    # elaborate wrong answer. Revisit if traces show successful third hops.
    max_retrieval_hops: int = 2
    # How many chunks survive reranking and reach the prompt.
    rerank_top_n: int = 6
    # How many of the fused candidates are worth an LLM opinion. The retrieval pool is
    # deliberately over-fetched for recall, but scoring all of it produced a ~9k-token
    # prompt that never finished inside the timeout - so every query paid the full wait
    # and then discarded the result. The weakest fusion candidates were never going to
    # survive the relevance floor anyway.
    rerank_candidate_limit: int = 12
    # The reranker is an LLM call; past this it is costing more than the recall it adds.
    # On timeout the pipeline falls back to raw fusion order rather than failing.
    rerank_timeout_seconds: float = 2.5
    # Relevance floor after reranking, applied per modality: ASR text scores lower than
    # typed prose at identical usefulness, so holding both to one bar silently drops
    # transcripts.
    rerank_relevance_threshold: float = 0.35
    rerank_asr_relevance_threshold: float = 0.25
    # Hard ceiling on assembled context. Enforced by dropping the lowest-ranked chunks, so
    # a generation call can never fail on overflow.
    context_token_budget: int = 8000
    # Verify citations before streaming rather than after. Off by default: it adds ~1.5s to
    # every answer and forces the whole response to be buffered, destroying time-to-first-
    # token. On for workspaces that would rather wait than be wrong.
    grounding_blocking: bool = False
    retrieval_top_k: int = 5
    retrieval_score_threshold: float = 0.25
    retrieval_min_context_chunks: int = 2
    # Each retrieval arm fetches top_k * this many candidates before fusion. Over-fetching is
    # what lets the score threshold be applied to a *pool* rather than to an already-truncated
    # list — a weak 5th match now gets replaced instead of leaving a hole. Keep the product
    # (5 * 6 = 30) under pgvector's default `hnsw.ef_search` of 40, or raise that to match.
    retrieval_candidate_multiplier: int = 6
    # Smoothing constant in Reciprocal Rank Fusion, from Cormack et al. (SIGIR 2009). Damps
    # the head of each ranking so one confident-but-wrong arm cannot dominate the other.
    retrieval_rrf_k: int = 60

    # --- Learned relevance prior ---
    # A bounded nudge to fusion order from what passages have actually done. Off until the
    # eval harness says it helps on a held-out split: a prior that entrenches looks exactly
    # like a prior that works if you only measure the questions it has already seen.
    retrieval_prior_enabled: bool = False
    # The furthest a passage can move on history alone, in ranks. Expressed in positions
    # rather than as a weight on the RRF value on purpose: at rrf_k=60 the fusion curve is
    # nearly flat (rank 0 and rank 5 differ by 0.0012), so a "fraction of one slot" bonus
    # is not a bound at all and lets a maximal prior take rank 0 from anywhere in the pool.
    # Three places reorders near-equals and cannot manufacture a top hit.
    retrieval_prior_max_rank_shift: int = 3
    # Where the logarithm flattens. At 10 supported citations a passage has essentially all
    # the standing it will ever get, so "cited 400 times" is not an unremovable pin.
    retrieval_prior_saturation: int = 10
    # A passage not cited for a month counts half as much. Corpora go stale; so should the
    # belief that a passage is the answer to something.
    retrieval_prior_half_life_days: float = 30.0
    # A human verdict outweighs the checker's, because it is the only signal in the pipeline
    # that does not come from a model grading its own work.
    feedback_upvote_weight: float = 2.0
    # Higher than the upvote on purpose: being wrong costs more than being right pays. The
    # asymmetry is what keeps the prior from being a ratchet that only ever goes up.
    feedback_downvote_weight: float = 3.0

    # --- Workspace memory ---
    # Facts that outlive a thread, injected as background into future prompts. Off by
    # default: it is the largest and least proven part of the flywheel, and a wrong memory
    # is worse than no memory because it is applied to questions it has nothing to do with.
    memory_enabled: bool = False
    memory_max_injected: int = 5
    # Memory's own slice of the context, SUBTRACTED from the assembler's budget at the
    # composition seam rather than added on top — so enabling memory can never push a
    # previously-fitting answer over the limit.
    memory_token_budget: int = 400
    # One distillation per three turns. Every turn would mean a model call per answer for a
    # table that gains a row a week.
    memory_distill_every_n_turns: int = 3
    # Enforced in code after the model returns, never asked for in the prompt: a memory is
    # injected into every future prompt, so its length is a cost paid forever.
    memory_max_chars: int = 300
    memory_max_per_call: int = 3
    # Jaccard overlap above which a new fact is treated as a restatement of a known one.
    memory_duplicate_threshold: float = 0.8

    filebase_access_key: str = ""
    filebase_secret_key: str = ""
    filebase_bucket_name: str = "kb-rag-new"
    filebase_endpoint: str = "https://s3.filebase.io"
    # In production the browser talks to the API same-origin (Caddy routes /api/* to it), so
    # this only matters in local dev where the Next apps run on their own ports.
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001"

    # --- Auth / tenancy ---
    # HS256 signing secret for access tokens. MUST be overridden in every real
    # environment (this default only keeps local dev booting).
    jwt_secret: str = "dev-insecure-change-me-in-every-real-environment-0123456789"
    jwt_algorithm: str = "HS256"
    # Access tokens are short-lived (revocation is handled by rotating refresh
    # tokens, not a per-request blocklist — see the auth plan). Refresh tokens are
    # long-lived and revocable in Postgres.
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60

    # Google sign-in. Only the (public) client id is needed — the browser-side ID-token flow
    # involves no client secret. Empty disables the feature: POST /auth/google returns 503
    # and the apps render no Google button, so local dev works without Google credentials.
    google_client_id: str = ""

    # --- Cache (Valkey) ---
    # No code path uses the cache today (it backed the removed cross-origin handoff). The
    # port and adapter are kept for the next thing that needs one.
    cache_url: str = "redis://localhost:6379/0"
    # Identical questions are common in a personal knowledge base. 0.97 cosine is close
    # enough to mean "the same question, differently typed" rather than "a related one".
    semantic_cache_threshold: float = 0.97
    semantic_cache_ttl_seconds: int = 3600
    # How many recent query embeddings to keep per tenant for that comparison. Capped
    # because each is 1536 floats and the whole point is to be cheaper than a model call.
    semantic_cache_size: int = 50
    embedding_cache_ttl_seconds: int = 30 * 24 * 60 * 60
    rerank_cache_ttl_seconds: int = 3600

    # --- Tracing (Langfuse) ---
    # Empty keys disable tracing entirely, so local development and CI need no account.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
