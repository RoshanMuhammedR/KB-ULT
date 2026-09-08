"""Turning retrieved chunks into a prompt, and into citations that match it.

The important thing here is that the numbering is built **once** and used by both. The
prompt says `[3]` and the citations list has an entry for 3 because they read the same
object, not because two loops happened to iterate in the same order. That correspondence
used to be positional and implicit, which is a silent-wrong-answer waiting to happen the
moment anything reorders one list and not the other — and multi-hop retrieval reorders
constantly.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from langchain_core.documents import Document

from src.domain.interfaces.repositories import IChunkRepository
from src.retrieval.langchain.retrievers import (
    ASSET_ID,
    CHUNK_ID,
    CHUNK_INDEX,
    FILENAME,
    LOCATOR,
    PARENT_ID,
    SCORE,
)

logger = structlog.get_logger(__name__)

#: Every child chunk of one section that matched this query. A citation names one section, but
#: several of its children can be hits, and all of them are evidence — for the eval's recall
#: and for the learned relevance prior. Before this they were dropped on the floor.
MATCHED_CHUNK_IDS = "matched_chunk_ids"

# Rough chars-per-token. Deliberately pessimistic: overestimating the budget truncates a
# little early, underestimating it fails the generation call outright.
_CHARS_PER_TOKEN = 3.5

_EXCERPT_CHARS = 500


@dataclass(slots=True)
class Citation:
    """One numbered source, as it appears in both the prompt and the response."""

    ordinal: int
    document: Document

    @property
    def chunk_id(self) -> str:
        return self.document.metadata.get(CHUNK_ID, "")

    @property
    def matched_chunk_ids(self) -> list[str]:
        """Every passage behind this citation, not only the one it is labelled with."""
        merged = self.document.metadata.get(MATCHED_CHUNK_IDS)
        if merged:
            return [chunk_id for chunk_id in merged if chunk_id]
        return [self.chunk_id] if self.chunk_id else []

    def to_wire(self) -> dict:
        metadata = self.document.metadata
        return {
            "asset_id": metadata.get(ASSET_ID),
            "chunk_id": metadata.get(CHUNK_ID),
            # Usually just `[chunk_id]`. Longer when several children of one section matched:
            # they collapse to a single citation for the reader, and every one of them is
            # still a passage that earned its place.
            "matched_chunk_ids": metadata.get(MATCHED_CHUNK_IDS) or [metadata.get(CHUNK_ID)],
            "filename": metadata.get(FILENAME),
            "source_type": metadata.get("source_type"),
            "locator": metadata.get(LOCATOR),
            "chunk_index": metadata.get(CHUNK_INDEX),
            # The reranker's judgement where it ran, the retrieval score otherwise. The UI
            # renders this as a relevance percentage, so it has to mean the same thing in
            # both cases: "how well this passage answers the question".
            "score": metadata.get("rerank_score", metadata.get(SCORE, 0.0)),
            "excerpt": self.document.page_content[:_EXCERPT_CHARS],
        }


@dataclass(slots=True)
class AssembledContext:
    citations: list[Citation]
    blocks: list[str]
    dropped: int

    @property
    def wire_citations(self) -> list[dict]:
        return [citation.to_wire() for citation in self.citations]


class ContextAssembler:
    """Expands matches to their sections, then fits them inside a hard token budget.

    **Parent expansion** is the payoff of small-to-big chunking: retrieval matched a
    precise child, and this substitutes the section that child came from, because a section
    is what actually contains enough to answer. Where a chunk has no parent — anything
    ingested before the hierarchy existed — it stands in for itself, so old and new
    documents both work.

    **No summarisation.** Two hops of six chunks is a few thousand tokens, comfortably
    inside any budget, so compressing them would spend latency and add a failure mode where
    the summariser drops the one sentence containing the answer. Deterministic truncation
    loses the lowest-ranked chunk instead, which is a loss you can reason about.
    """

    def __init__(self, chunk_repo: IChunkRepository, *, token_budget: int) -> None:
        self.chunk_repo = chunk_repo
        self.token_budget = token_budget

    async def assemble(self, documents: list[Document]) -> AssembledContext:
        expanded = await self._expand(documents)

        citations: list[Citation] = []
        blocks: list[str] = []
        used = 0
        dropped = 0

        for document in expanded:
            block_text = document.page_content
            cost = len(block_text) / _CHARS_PER_TOKEN
            if used + cost > self.token_budget and citations:
                # Everything below here is lower-ranked than what already fits. Dropping
                # from the bottom is why a generation call can never fail on overflow.
                dropped += 1
                continue

            ordinal = len(citations) + 1
            citations.append(Citation(ordinal=ordinal, document=document))
            blocks.append(self._render(ordinal, document))
            used += cost

        if dropped:
            logger.info("context_truncated", kept=len(citations), dropped=dropped)

        return AssembledContext(citations=citations, blocks=blocks, dropped=dropped)

    async def _expand(self, documents: list[Document]) -> list[Document]:
        parent_ids = [
            document.metadata[PARENT_ID]
            for document in documents
            if document.metadata.get(PARENT_ID)
        ]
        if not parent_ids:
            return documents

        from uuid import UUID

        parents = await self.chunk_repo.list_parents([UUID(pid) for pid in parent_ids])

        expanded: list[Document] = []
        seen_parents: set[str] = set()
        by_parent: dict[str, Document] = {}
        for document in documents:
            parent_id = document.metadata.get(PARENT_ID)
            parent = parents.get(UUID(parent_id)) if parent_id else None
            if parent is None:
                expanded.append(document)
                continue
            # Two children of one section expand to the same parent. Send it once: the
            # second copy would consume budget to say what the first already said, and it
            # would give one section two citation numbers.
            #
            # But the other children are *recorded*, not forgotten. Dropping them outright
            # meant a passage that matched alongside a sibling contributed nothing anywhere:
            # it was invisible to the eval's recall (so a multi-hop case whose two expected
            # chunks shared one section was capped at 0.5 however good retrieval was), and
            # invisible to `_record_signals`, so the learned prior never learned from it.
            if parent_id in seen_parents:
                by_parent[parent_id].metadata[MATCHED_CHUNK_IDS].append(
                    document.metadata.get(CHUNK_ID)
                )
                continue
            seen_parents.add(parent_id)
            block = Document(
                page_content=parent.text,
                # The child's metadata is kept: its locator is where the *match* was,
                # which is what a citation should point the reader at.
                metadata={
                    **document.metadata,
                    "expanded_from_child": True,
                    # Every child of this section that matched. The first is the one the
                    # locator and excerpt describe.
                    MATCHED_CHUNK_IDS: [document.metadata.get(CHUNK_ID)],
                },
            )
            by_parent[parent_id] = block
            expanded.append(block)
        return expanded

    @staticmethod
    def _render(ordinal: int, document: Document) -> str:
        metadata = document.metadata
        locator = metadata.get(LOCATOR)
        position = locator.get("value") if isinstance(locator, dict) else None
        heading = metadata.get("heading")
        score = metadata.get("rerank_score", metadata.get(SCORE, 0.0))

        header = f"[{ordinal}] source={metadata.get(FILENAME)}"
        if position is not None:
            header += f" at={position}"
        if heading:
            header += f" section={heading}"
        header += f" score={score:.3f}"

        # The delimiters and the label are load-bearing, not decoration: this text comes
        # from an uploaded document and may contain anything, including instructions
        # addressed to the model. See the system prompt in prompts.py.
        return f"{header}\n<document>\n{document.page_content}\n</document>"
