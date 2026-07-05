from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILES = tuple(parent / ".env" for parent in reversed(Path(__file__).resolve().parents))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(*ENV_FILES, ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://kb_user:kb_password@localhost:5432/kb_new"
    aicredits_api_key: str = ""
    aicredits_base_url: str = "https://api.aicredits.in/v1"
    aicredits_chat_model: str = "openai/gpt-4o-mini"
    aicredits_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    chunk_size_tokens: int = 800
    chunk_overlap_tokens: int = 120
    retrieval_top_k: int = 5
    retrieval_score_threshold: float = 0.25
    retrieval_min_context_chunks: int = 2

    filebase_access_key: str = ""
    filebase_secret_key: str = ""
    filebase_bucket_name: str = "kb-rag-new"
    filebase_endpoint: str = "https://s3.filebase.io"


@lru_cache
def get_settings() -> Settings:
    return Settings()
