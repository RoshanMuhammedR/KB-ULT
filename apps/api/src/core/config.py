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
    aicredits_api_key: str = ""
    aicredits_base_url: str = "https://api.aicredits.in/v1"
    aicredits_chat_model: str = "openai/gpt-4o-mini"
    aicredits_embedding_model: str = "text-embedding-3-small"
    # Hosted speech-to-text for audio sources. Nothing runs locally — no ML runtime, no
    # weights in the image — so this is just another model id on the same gateway.
    aicredits_transcription_model: str = "mistralai/voxtral-small-24b-2507"
    embedding_dimensions: int = 1536

    # Audio is transcribed by a paid hosted model, so it gets a size cap the other source
    # types don't need. Enforced at upload with a plain-language 400.
    max_audio_upload_bytes: int = 100 * 1024 * 1024

    chunk_size_tokens: int = 800
    chunk_overlap_tokens: int = 120
    retrieval_top_k: int = 5
    retrieval_score_threshold: float = 0.25
    retrieval_min_context_chunks: int = 2

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

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
