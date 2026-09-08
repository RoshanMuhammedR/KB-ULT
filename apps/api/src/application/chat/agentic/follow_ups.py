"""Questions worth asking next, drawn from what was actually retrieved.

**Grounded in the passages, not in the topic.** The obvious way to build this is to hand a
model the question and the answer and ask for three more questions — which reliably produces
questions the corpus cannot answer, because nothing in that prompt knows what the corpus
contains. A suggestion that leads to "I could not find this" is worse than no suggestion: the
product offered it, so the failure reads as the product's.

So the sources and headings that were retrieved go in too, and the instruction is to propose
only what those passages could answer.

Runs after `done`, beside the grounding check, on the fast model. The reader is not waiting
for it, and an answer that arrives without suggestions is an answer.
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "You propose the next questions a reader would ask, for a search tool over their own "
    "documents.\n\n"
    "Rules:\n"
    "- Propose ONLY questions the listed passages could answer. You are looking at "
    "everything the tool found; anything outside it will fail.\n"
    "- Do not restate the question that was just answered.\n"
    "- Each question stands alone, with no 'it' or 'that' referring back.\n"
    "- Short and specific. A question naming a thing beats a question about a theme.\n"
    "- Two or three. Fewer is fine. None is fine when nothing follows naturally."
)

_USER = (
    "They asked: {question}\n\n"
    "They were told: {answer}\n\n"
    "Passages the tool found:\n{passages}"
)

#: More than this is a menu, not a suggestion.
_MAX = 3
#: How much of each passage the suggester sees. It needs to know what a passage is *about*,
#: which the heading and opening line carry; the rest is cost.
_PASSAGE_CHARS = 300


class _FollowUps(BaseModel):
    questions: list[str] = Field(default_factory=list, description="Two or three, or none")


class FollowUpSuggester:
    """Suggests next questions the corpus can actually answer."""

    def __init__(self, llm, *, max_suggestions: int = _MAX) -> None:
        self.llm = llm
        self.max_suggestions = max_suggestions

    async def suggest(self, question: str, answer: str, citations) -> list[str]:
        """Returns [] on any failure, and on an answer that found nothing.

        A refusal has nothing to follow up: suggesting questions after "I could not find
        this" invites the reader to try three more things that will also fail.
        """
        if not citations:
            return []

        passages = "\n\n".join(
            f"- {citation.document.metadata.get('filename', 'source')}"
            f" ({citation.document.metadata.get('heading') or 'section'}): "
            f"{citation.document.page_content[:_PASSAGE_CHARS]}"
            for citation in citations
        )

        try:
            structured = self.llm.with_structured_output(_FollowUps)
            result: _FollowUps = await structured.ainvoke(
                [
                    {"role": "system", "content": _SYSTEM},
                    {
                        "role": "user",
                        "content": _USER.format(
                            question=question, answer=answer[:2000], passages=passages
                        ),
                    },
                ]
            )
        except Exception:  # noqa: BLE001 - no suggestions is a fine outcome; an error is not
            logger.warning("follow_ups_unavailable")
            return []

        # Capped after the model returns rather than trusted from the prompt, and deduplicated
        # against the question just asked so the reader is not offered it back.
        asked = question.strip().casefold()
        seen: set[str] = set()
        suggestions: list[str] = []
        for candidate in result.questions:
            text = candidate.strip()
            key = text.casefold()
            if not text or key == asked or key in seen:
                continue
            seen.add(key)
            suggestions.append(text)

        return suggestions[: self.max_suggestions]
