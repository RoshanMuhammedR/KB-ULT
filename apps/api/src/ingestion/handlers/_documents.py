"""Shared `Document`-building helpers for timed transcripts.

Both the YouTube and audio handlers receive the same shape from very different places —
a list of `{text, start}` lines, each too short to cite on its own — and need the same
thing out of it: citation-sized `Document`s stamped with the start time of their first
line. That logic lives here so the two handlers cannot drift apart.
"""

from __future__ import annotations

from langchain_core.documents import Document

from src.core.text import sanitize_text_for_storage

# Coalesce transcript lines into windows of roughly this many characters. Transcript
# entries are tiny (a few words each); grouping them yields citation-friendly documents
# while the start time of each group becomes the citation locator.
WINDOW_CHAR_TARGET = 500


def coalesce_timed_lines(
    lines: list[dict],
    *,
    char_target: int = WINDOW_CHAR_TARGET,
) -> list[Document]:
    """Group consecutive `{text, start}` lines into ~`char_target` windows.

    Each window keeps its first line's start time as a `timestamp` locator (whole seconds).
    A window is flushed *before* adding a line that would overflow it, so windows stay
    bounded and the timestamp always points at text the window actually contains.
    """
    documents: list[Document] = []
    buffer: list[str] = []
    window_start = 0.0
    current_len = 0

    for line in lines:
        text = line.get("text") or ""
        if buffer and current_len + len(text) > char_target:
            _emit(documents, buffer, window_start)
            buffer = []
            current_len = 0
        if not buffer:
            window_start = float(line.get("start", 0) or 0)
        buffer.append(text)
        current_len += len(text)

    _emit(documents, buffer, window_start)
    return documents


def _emit(documents: list[Document], buffer: list[str], window_start: float) -> None:
    if not buffer:
        return
    text = sanitize_text_for_storage(" ".join(buffer)).strip()
    if text:
        documents.append(
            Document(
                page_content=text,
                metadata={"locator": {"type": "timestamp", "value": int(window_start)}},
            )
        )


def split_untimed_text(text: str, *, char_target: int = WINDOW_CHAR_TARGET) -> list[Document]:
    """Fallback for a transcript that came back as plain text with no timings.

    Locators degrade honestly to `section` "Part N" rather than inventing timestamps the
    provider never gave us — the UI reads that and starts the player from the beginning
    instead of seeking to a second it cannot justify.
    """
    cleaned = sanitize_text_for_storage(text).strip()
    if not cleaned:
        return []

    documents: list[Document] = []
    buffer: list[str] = []
    current_len = 0

    def flush() -> None:
        if not buffer:
            return
        joined = " ".join(buffer).strip()
        if joined:
            documents.append(
                Document(
                    page_content=joined,
                    metadata={
                        "locator": {"type": "section", "value": f"Part {len(documents) + 1}"}
                    },
                )
            )

    # Split on sentence-ish boundaries first so a window rarely cuts mid-sentence.
    for piece in cleaned.replace("\n", " ").split(". "):
        piece = piece.strip()
        if not piece:
            continue
        piece = piece if piece.endswith(".") else f"{piece}."
        if buffer and current_len + len(piece) > char_target:
            flush()
            buffer = []
            current_len = 0
        buffer.append(piece)
        current_len += len(piece)

    flush()
    return documents
