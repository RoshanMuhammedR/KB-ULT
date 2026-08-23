"""The answer given when there is nothing to answer from.

A template, never generation. The moment a model is asked to write "I couldn't find that",
it can also write a plausible-sounding answer from its own weights — which is precisely the
failure a citation-backed system exists to prevent, arriving at exactly the moment the user
has least ability to catch it.

The template is enriched with evidence that the system *looked*: which sources were
searched, and anything it found that scored too low to use. "I don't know" is much easier to
trust when it comes with proof of where you looked.
"""

from __future__ import annotations

import structlog
from langchain_core.documents import Document

from src.retrieval.langchain.retrievers import FILENAME, SCORE

logger = structlog.get_logger(__name__)

NOT_FOUND = (
    "I couldn't find information about this in your knowledge base. Try rephrasing the "
    "question, or this may not be covered by the sources you've added."
)

FAILED = (
    "Something went wrong while answering. Nothing was saved, so you can ask this again "
    "as-is."
)


def not_found_answer(
    *,
    searched_sources: list[str],
    near_misses: list[Document] | None = None,
) -> str:
    """The not-found template, with what evidence there is."""
    parts = [NOT_FOUND]

    if searched_sources:
        listed = ", ".join(sorted(set(searched_sources))[:5])
        more = len(set(searched_sources)) - 5
        suffix = f" and {more} more" if more > 0 else ""
        parts.append(f"\n\nI searched: {listed}{suffix}.")

    if near_misses:
        # Labelled unmistakably. These scored below the relevance floor, so presenting them
        # as anything other than "possibly not what you want" would undo the floor.
        parts.append("\n\nRelated, but possibly not what you're looking for:")
        for document in near_misses[:3]:
            name = document.metadata.get(FILENAME, "a source")
            excerpt = " ".join(document.page_content.split())[:160]
            parts.append(f'\n- {name}: "{excerpt}…"')

    return "".join(parts)


def searched_source_names(documents: list[Document]) -> list[str]:
    return [
        document.metadata.get(FILENAME)
        for document in documents
        if document.metadata.get(FILENAME)
    ]


def rank_near_misses(documents: list[Document]) -> list[Document]:
    return sorted(documents, key=lambda d: d.metadata.get(SCORE, 0.0), reverse=True)
