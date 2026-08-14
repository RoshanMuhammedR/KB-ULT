"""Naming a conversation from its opening question.

Deliberately not an LLM call: the first question is almost always the best label a thread
could have, and a second round-trip before the user sees any answer is the wrong place to
spend a second. The user can rename it afterwards.
"""

from __future__ import annotations

MAX_TITLE_LENGTH = 80

# Trailing punctuation reads as noise once the question is a heading.
_TRAILING = " \t\n?.!,;:"


def title_from_question(question: str, max_length: int = MAX_TITLE_LENGTH) -> str:
    """Collapse a question into a short title, truncated at a word boundary."""
    cleaned = " ".join(question.split()).strip(_TRAILING)
    if not cleaned:
        return "New conversation"

    if len(cleaned) <= max_length:
        return cleaned

    # Cut at the last whole word that fits, then re-trim punctuation the cut exposed.
    window = cleaned[: max_length + 1]
    cut = window.rfind(" ")
    truncated = (window[:cut] if cut > 0 else cleaned[:max_length]).strip(_TRAILING)
    return f"{truncated}…" if truncated else cleaned[:max_length]
