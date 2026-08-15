"""Shared segment-building helpers for timed transcripts.

Both the YouTube and audio handlers receive the same shape from very different places —
a list of `{text, start}` lines, each too short to cite on its own — and need the same
thing out of it: citation-sized segments stamped with the start time of their first line.
That logic lives here so the two handlers cannot drift apart.
"""

from __future__ import annotations

from src.core.text import sanitize_text_for_storage

# Coalesce transcript lines into segments of roughly this many characters. Transcript
# entries are tiny (a few words each); grouping them yields citation-friendly chunks while
# the start time of each group becomes the citation locator.
SEGMENT_CHAR_TARGET = 500


def coalesce_timed_lines(
    lines: list[dict],
    *,
    char_target: int = SEGMENT_CHAR_TARGET,
) -> list[dict]:
    """Group consecutive `{text, start}` lines into ~`char_target` windows.

    Each window keeps its first line's start time as a `timestamp` locator (whole seconds).
    A window is flushed *before* adding a line that would overflow it, so windows stay
    bounded and the timestamp always points at text the window actually contains.
    """
    segments: list[dict] = []
    buffer: list[str] = []
    window_start = 0.0
    window_end = 0.0
    current_len = 0

    for line in lines:
        text = line.get("text") or ""
        if buffer and current_len + len(text) > char_target:
            _emit(segments, buffer, window_start, window_end)
            buffer = []
            current_len = 0
        if not buffer:
            window_start = float(line.get("start", 0) or 0)
        # Track the far edge of the window as it grows. Each line's end is its own start plus
        # its duration; `max` guards transcripts whose lines overlap or arrive out of order.
        line_start = float(line.get("start", 0) or 0)
        window_end = max(window_end, line_start + float(line.get("duration", 0) or 0))
        buffer.append(text)
        current_len += len(text)

    _emit(segments, buffer, window_start, window_end)
    return segments


def _emit(segments: list[dict], buffer: list[str], window_start: float, window_end: float) -> None:
    if not buffer:
        return
    text = sanitize_text_for_storage(" ".join(buffer)).strip()
    if not text:
        return
    # The locator stays an int for `formatLocator`, which renders it as a clock time and is
    # shared with both frontends — changing its type would break every citation label.
    # The float span rides alongside as `region`: it is what lets a player highlight the
    # passage rather than just seek to its first second. `duration` used to be discarded
    # entirely, so no segment had an end at all.
    segment: dict = {"text": text, "locator": {"type": "timestamp", "value": int(window_start)}}
    if window_end > window_start:
        segment["region"] = {"start": round(window_start, 2), "end": round(window_end, 2)}
    segments.append(segment)


def split_untimed_text(text: str, *, char_target: int = SEGMENT_CHAR_TARGET) -> list[dict]:
    """Fallback for a transcript that came back as plain text with no timings.

    Locators degrade honestly to `section` "Part N" rather than inventing timestamps the
    provider never gave us — the UI reads that and starts the player from the beginning
    instead of seeking to a second it cannot justify.
    """
    cleaned = sanitize_text_for_storage(text).strip()
    if not cleaned:
        return []

    segments: list[dict] = []
    buffer: list[str] = []
    current_len = 0

    def flush() -> None:
        if not buffer:
            return
        joined = " ".join(buffer).strip()
        if joined:
            segments.append(
                {"text": joined, "locator": {"type": "section", "value": f"Part {len(segments) + 1}"}}
            )

    # Split on sentence-ish boundaries first so a segment rarely cuts mid-sentence.
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
    return segments
