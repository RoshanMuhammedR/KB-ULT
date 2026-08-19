from langchain_openai import OpenAIEmbeddings

from src.infrastructure.ai_providers.circuit_breaker import get_breaker

# The library default is 600s with no cap on how long a hung gateway holds the caller. An
# embed call blocks a worker slot (ingestion) or an anyio thread plus a DB session (query
# embedding) for its whole duration, so giving up early and letting the queue's
# RetryStrategy(3, exponential 5s) drive the retry is strictly better than hanging. Kept in
# step with the chat adapter, which made the same trade for the same reason.
_REQUEST_TIMEOUT_SECONDS = 60.0
# One in-client retry absorbs a single 429/blip without waiting for the ~5s job backoff;
# beyond that the job-level retry is the right place, since re-embedding is idempotent.
_MAX_RETRIES = 1


class OpenAICompatibleEmbeddingsAdapter:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.client = OpenAIEmbeddings(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            max_retries=_MAX_RETRIES,
        )
        # Separate from the chat breaker: the two are different endpoints on the gateway and
        # one can be degraded while the other serves fine. Sharing state would take the
        # working half down with the broken one.
        self._breaker = get_breaker("embeddings")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._breaker.call(self.client.embed_documents, texts)

    def embed_query(self, text: str) -> list[float]:
        return self._breaker.call(self.client.embed_query, text)
