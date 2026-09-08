"""LangChain retrievers over this app's own tenant-scoped storage.

**Why not `langchain_postgres.PGVector`.** It owns its own tables and its own connection,
which means queries issued through it never pass the `do_orm_execute` tenant filter and never
carry the transaction-local GUC that Postgres RLS reads. Adopting it would silently reduce a
two-layer isolation guarantee to zero layers. So the composition, fusion and compression
above this file are all LangChain; the data access underneath stays ours.

Everything here converts between the two vocabularies exactly once: repositories speak
`RetrievalResult(chunk, asset, score)`, LangChain speaks `Document(page_content, metadata)`.
Doing it at this boundary means nothing downstream needs to know both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from langchain_core.callbacks import AsyncCallbackManagerForRetrieverRun, CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from src.domain.entities import RetrievalResult

if TYPE_CHECKING:  # the annotation is real; the runtime import is not needed
    from src.domain.interfaces import IVectorStore

logger = structlog.get_logger(__name__)

# Metadata keys the rest of the pipeline reads off a Document. Named here so the citation
# builder and the reranker are not each guessing at strings.
CHUNK_ID = "chunk_id"
ASSET_ID = "asset_id"
PARENT_ID = "parent_id"
SCORE = "score"
MODALITY = "modality"
LOCATOR = "locator"
FILENAME = "filename"
CHUNK_INDEX = "chunk_index"


def to_document(result: RetrievalResult) -> Document:
    """The single conversion point from a repository row to a LangChain Document."""
    return Document(
        # The displayed text, never the enriched embedding text: everything downstream —
        # the prompt, the citation excerpt, the grounding check — is about what the source
        # actually says.
        page_content=result.chunk.text,
        metadata={
            CHUNK_ID: str(result.chunk.id),
            ASSET_ID: str(result.asset.id),
            PARENT_ID: str(result.chunk.parent_id) if result.chunk.parent_id else None,
            SCORE: result.score,
            MODALITY: result.chunk.modality,
            LOCATOR: result.chunk.metadata.get("locator"),
            FILENAME: result.asset.filename,
            CHUNK_INDEX: result.chunk.chunk_index,
            "heading": result.chunk.metadata.get("heading"),
            "source_type": result.asset.source_type,
        },
    )


class _ChunkRetriever(BaseRetriever):
    """Shared plumbing: async-only, tenant-scoped, Document-emitting.

    The sync path raises rather than blocking. A retriever that quietly ran a database call
    on the event loop would be a latency bug that only appears under load, so it fails
    loudly at the one call site that could introduce it.
    """

    # `BaseRetriever` is a pydantic model, and a bare `Protocol` cannot be used as an
    # isinstance check, so the annotation is `Any` with the real contract stated here:
    # this is an `IVectorStore`. Runtime validation would buy nothing anyway — the only
    # thing that ever constructs these is the composition root.
    vector_store: Any
    #: Every base attached to this chat. Retrieval spans all of them.
    knowledge_base_ids: list[UUID]
    limit: int

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        raise NotImplementedError(
            f"{type(self).__name__} is async-only; use `ainvoke`. A synchronous call here "
            "would run a database query on the event loop."
        )


class DenseChunkRetriever(_ChunkRetriever):
    """Vector search: nearest neighbours of the query embedding, over the HNSW index."""

    query_embedding: list[float]
    threshold: float

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
    ) -> list[Document]:
        results = await self.vector_store.search_dense(
            self.query_embedding, self.knowledge_base_ids, self.limit, self.threshold
        )
        return [to_document(result) for result in results]


class LexicalChunkRetriever(_ChunkRetriever):
    """Full-text search over `chunks.fts`.

    Exists because dense retrieval fails predictably on the tokens that carry no semantic
    weight but total precision: error codes, config keys, version numbers, rare proper
    nouns. A chunk can contain `ERR_CONN_REFUSED` verbatim and still not be retrieved for a
    query that is exactly that string.
    """

    query_embedding: list[float]

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
    ) -> list[Document]:
        if not query.strip():
            return []
        results = await self.vector_store.search_lexical(
            self.query_embedding, query, self.knowledge_base_ids, self.limit
        )
        return [to_document(result) for result in results]


def build_hybrid_retriever(
    vector_store: IVectorStore,
    query_embedding: list[float],
    knowledge_base_ids: list[UUID],
    *,
    limit: int,
    threshold: float,
    rrf_k: int,
) -> Any:
    """Both arms, fused with Reciprocal Rank Fusion.

    `EnsembleRetriever` implements exactly the RRF this codebase already had — `score =
    Σ weight / (k + rank)`, default k=60 from Cormack et al. — so the hand-written
    `fusion.py` is retired rather than duplicated.

    Fusing on rank instead of score is the point: cosine similarity is bounded 0-1 while
    `ts_rank_cd` is unbounded and corpus-dependent, so any attempt to normalise them into a
    common scale is an invented mapping that drifts as the corpus grows. Ranks need no such
    mapping, and an item found by *both* arms outranks one found brilliantly by only one.

    **Known fragility, worth fixing properly.** `EnsembleRetriever.arank_fusion` runs the two
    arms under `asyncio.gather`, and both share this request's single `AsyncSession` — which
    SQLAlchemy explicitly does not support for concurrent use. It survives only because the
    connection is already established by the time retrieval runs, so the two greenlets
    serialise on it by luck rather than design. Anything that ends the transaction earlier in
    the request re-exposes it: a mid-answer `commit()` returns the connection to the pool and
    the two arms then race to provision a new one, which fails the whole answer with
    "this session is provisioning a new connection". That is exactly what a `commit` in
    `MemoryRepository.touch` did. The durable fix is a session per arm; until then, nothing
    on the answer path may commit before this point.
    """
    from langchain_classic.retrievers import EnsembleRetriever

    dense = DenseChunkRetriever(
        vector_store=vector_store,
        knowledge_base_ids=knowledge_base_ids,
        limit=limit,
        query_embedding=query_embedding,
        threshold=threshold,
    )
    lexical = LexicalChunkRetriever(
        vector_store=vector_store,
        knowledge_base_ids=knowledge_base_ids,
        limit=limit,
        query_embedding=query_embedding,
    )
    return EnsembleRetriever(
        retrievers=[dense, lexical],
        # Equal weight. The retriever logs how many winners the lexical arm contributed
        # that dense had not already found, which is the number that would justify changing
        # this — tuning it on intuition would be worse than leaving it alone.
        weights=[1.0, 1.0],
        c=rrf_k,
        id_key=CHUNK_ID,
    )
