"""Caches on the query path, all of them best-effort and all of them tenant-safe.

Three separate caches, because they key on different things and go stale for different
reasons:

* **Embeddings** are keyed on the *content* being embedded. Global, and safe to share: you
  must already possess the text to compute the key, so a hit reveals nothing you did not
  bring with you. This is the one that saves real money — re-ingesting an unchanged
  document costs nothing.

* **Rerank verdicts** are keyed on the query plus the exact candidate set. Tenant-scoped,
  because the candidates are the tenant's documents.

* **Answers** are keyed on the query *semantically* — the same question typed twice is
  rarely typed identically. Tenant-scoped, and invalidated whenever that workspace ingests
  something, because the corpus the answer was drawn from has changed.

Every key goes through `tenant_cache_key`, which raises when no tenant is bound. A cache
that quietly served one tenant's answer to another would be the most expensive bug in the
system, so the key builder fails closed rather than defaulting to a shared namespace.
"""

from __future__ import annotations

import hashlib
import json
import math

import structlog

from src.domain.interfaces.cache import ICache
from src.infrastructure.cache.keys import system_cache_key, tenant_cache_key

logger = structlog.get_logger(__name__)


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


class EmbeddingCache:
    """Content-addressed embedding cache, wrapping any `IEmbedder`.

    Keyed on `sha256(text) + model + dimensions`, so it is correct across tenants and across
    documents: the same paragraph in two files embeds once. The model id is in the key because
    two models produce different vectors for identical text, and serving one where the other
    was expected corrupts the index silently.

    **Dimensions are in the key too, and were not.** A gateway can serve a different vector
    width under the same model id, and `embedding_dimensions` is a setting someone can change.
    Either way the cache would have handed back a vector of the wrong length under an
    unchanged key, and pgvector would have been asked to compare it against a column of a
    different width — a runtime failure whose cause is three layers away from where it shows.

    The length is also checked on read. A key can only collide if the content, model and
    dimensions all match, so a wrong-length hit means something else wrote that key; returning
    it would let whatever did so choose the query vector for every tenant asking that question.
    """

    def __init__(
        self, inner, cache: ICache, *, model: str, ttl_seconds: int, dimensions: int | None = None
    ) -> None:
        self.inner = inner
        self.cache = cache
        self.model = model
        self.ttl_seconds = ttl_seconds
        self.dimensions = dimensions

    async def embed_query(self, text: str) -> list[float]:
        key = system_cache_key(
            "embedding", self.model, str(self.dimensions or "default"), _digest(text)
        )
        hit = await self.cache.get(key)
        if hit:
            cached = self._valid(hit, key)
            if cached is not None:
                return cached

        vector = await self.inner.embed_query(text)
        await self.cache.set(key, json.dumps(vector), ttl_seconds=self.ttl_seconds)
        return vector

    def _valid(self, hit: str, key: str) -> list[float] | None:
        """A cached vector, or None if it cannot be trusted.

        Anything unusable is treated as a miss rather than raised: the real embedder is one
        call away, and failing a question over a bad cache entry would be a worse outcome
        than paying for it again.
        """
        try:
            vector = json.loads(hit)
        except json.JSONDecodeError:
            logger.warning("embedding_cache_corrupt", key=key, reason="not_json")
            return None

        if not isinstance(vector, list) or not all(isinstance(v, (int, float)) for v in vector):
            logger.warning("embedding_cache_corrupt", key=key, reason="not_a_vector")
            return None

        if self.dimensions and len(vector) != self.dimensions:
            logger.warning(
                "embedding_cache_corrupt",
                key=key,
                reason="wrong_dimensions",
                got=len(vector),
                expected=self.dimensions,
            )
            return None

        return vector

    async def embed_texts(self, texts: list[str]):
        # Ingestion embeds in batches, and a partial-hit batch would need the misses
        # re-batched and the results re-interleaved. That is worth doing when the ingestion
        # volume justifies it; until then the batch path stays honest and uncached rather
        # than subtly mis-ordered.
        return await self.inner.embed_texts(texts)


class RerankCache:
    """Memoises a rerank verdict for one query over one exact candidate set.

    Hits mostly on retries and on the second hop of a loop that re-found the same
    candidates — which is exactly when paying for the same judgement twice would be most
    annoying.
    """

    def __init__(self, cache: ICache, *, ttl_seconds: int) -> None:
        self.cache = cache
        self.ttl_seconds = ttl_seconds

    async def get(self, query: str, candidate_ids: list[str]) -> dict[str, float] | None:
        raw = await self.cache.get(self._key(query, candidate_ids))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set(self, query: str, candidate_ids: list[str], scores: dict[str, float]) -> None:
        await self.cache.set(
            self._key(query, candidate_ids), json.dumps(scores), ttl_seconds=self.ttl_seconds
        )

    @staticmethod
    def _key(query: str, candidate_ids: list[str]) -> str:
        # Sorted: the same candidates in a different order are the same judgement.
        return tenant_cache_key("rerank", _digest(query, *sorted(candidate_ids)))


class SemanticAnswerCache:
    """Serves a stored answer when the same question is asked again in different words.

    Exact-match caching almost never hits — people rephrase. Comparing embeddings does hit,
    but a vector index per tenant would cost more than it saves at this scale, so this keeps
    a small bounded list of recent query embeddings and compares in Python. Fifty entries of
    1536 floats is a few hundred kilobytes per active tenant and a sub-millisecond scan; a
    model call is neither.

    The threshold is deliberately high (0.97). At that similarity the questions are the same
    question typed twice, not two related questions — and serving a related question's
    answer is worse than not caching at all.
    """

    def __init__(self, cache: ICache, *, threshold: float, ttl_seconds: int, max_entries: int) -> None:
        self.cache = cache
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

    async def find(self, embedding: list[float]) -> dict | None:
        entries = await self._entries()
        best, best_score = None, 0.0
        for entry in entries:
            score = _cosine(embedding, entry.get("embedding", []))
            if score > best_score:
                best, best_score = entry, score

        if best is None or best_score < self.threshold:
            return None

        payload = await self.cache.get(tenant_cache_key("answer", best["key"]))
        if not payload:
            return None
        try:
            answer = json.loads(payload)
        except json.JSONDecodeError:
            return None
        logger.info("semantic_cache_hit", similarity=round(best_score, 4))
        return answer

    async def store(self, embedding: list[float], answer: dict) -> None:
        key = _digest(json.dumps(embedding[:8]), answer.get("answer", "")[:64])
        await self.cache.set(
            tenant_cache_key("answer", key), json.dumps(answer), ttl_seconds=self.ttl_seconds
        )

        entries = await self._entries()
        entries.append({"key": key, "embedding": embedding})
        # Newest first, bounded. An unbounded list would turn a cheap scan into an expensive
        # one exactly for the tenants who use the product most.
        entries = entries[-self.max_entries :]
        await self.cache.set(
            tenant_cache_key("answer_index"), json.dumps(entries), ttl_seconds=self.ttl_seconds
        )

    async def invalidate(self) -> None:
        """Drop this tenant's answers. Called on ingest: the corpus changed, so every
        cached answer was drawn from a knowledge base that no longer exists."""
        await self.cache.delete(tenant_cache_key("answer_index"))

    async def _entries(self) -> list[dict]:
        raw = await self.cache.get(tenant_cache_key("answer_index"))
        if not raw:
            return []
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return entries if isinstance(entries, list) else []


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)
