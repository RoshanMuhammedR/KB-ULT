"""Distilling durable facts out of a conversation, and choosing which to recall.

**The security decision that shapes this whole module: the distiller sees the question and
the answer, and never the retrieved context.**

A memory is injected into *every future prompt* in the workspace. That makes this a far
nastier injection surface than the answer path, where a poisoned document influences one
response and is gone. A single sentence from a malicious PDF that reaches
`workspace_memories` has achieved persistence — it would be recalled and injected for months,
against questions that have nothing to do with the document it came from, long after anyone
would think to connect the two.

The answer is not "prompt the distiller to be careful". Prompt instructions are the weakest
defence available and this is the highest-value target in the system. So the untrusted text
is structurally absent from the call: the distiller receives the user's own question and the
model's own answer, both of which have already passed through the answering model's
untrusted-content handling. Whatever survives into a memory has been through that filter
once and is a claim the assistant made, not a string an attacker wrote.

The remaining limits — length, count — are enforced in code after the model returns, never
asked for in the prompt. A model that ignores "at most three facts" is not a bug worth
retrying; it is the normal case that the caller must already handle.
"""

from __future__ import annotations

import re
from uuid import UUID

import structlog
from pydantic import BaseModel, Field

from src.domain.entities import Memory, MemoryKind

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "You extract durable facts from a conversation, for a knowledge assistant that will "
    "remember them in future conversations.\n\n"
    "Record a fact only if ALL of these hold:\n"
    "  - it is about the user, their team, or how they want to be answered\n"
    "  - it will still be true and useful weeks from now\n"
    "  - it is not already implied by the documents in their library\n\n"
    "Do NOT record: the answer to the question itself, anything specific to this one "
    "conversation, or anything the user did not state about themselves.\n\n"
    "Most conversations contain nothing worth remembering. Returning an empty list is the "
    "expected outcome and is always better than recording something marginal.\n\n"
    "If a fact contradicts one of the existing memories you were shown, set `supersedes` to "
    "that memory's number."
)

_USER = (
    "Existing memories:\n{memories}\n\n"
    "Question: {question}\n\n"
    "Answer given: {answer}"
)


class _Candidate(BaseModel):
    content: str = Field(description="One short sentence, in the third person")
    kind: str = Field(description='"fact" or "preference"', default="fact")
    supersedes: int | None = Field(
        default=None, description="Number of an existing memory this replaces, if any"
    )


class _Distilled(BaseModel):
    facts: list[_Candidate] = Field(default_factory=list)


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def similarity(left: str, right: str) -> float:
    """Jaccard overlap of two memories' word sets.

    A pure function over lowercased tokens, deliberately crude. Dedup here is protecting
    against the same fact being restated in slightly different words across conversations,
    which is a lexical problem — not against two genuinely different facts that happen to be
    semantically close, which an embedding would conflate and a human would not. Being pure
    also means the threshold can be tuned against real examples in a unit test, with no
    database and no model call.
    """
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


class MemoryService:
    """Reads memories for a prompt, and writes new ones from a finished conversation."""

    def __init__(
        self,
        llm,
        repo,
        *,
        max_injected: int,
        max_chars: int,
        max_per_call: int,
        duplicate_threshold: float,
        token_budget: int,
    ) -> None:
        self.llm = llm
        self.repo = repo
        self.max_injected = max_injected
        self.max_chars = max_chars
        self.max_per_call = max_per_call
        self.duplicate_threshold = duplicate_threshold
        self.token_budget = token_budget

    async def recall(self, knowledge_base_id: UUID, keywords: str) -> list[Memory]:
        """The memories worth putting in front of this question, within budget.

        Failure is silent and total: an answer without memory is the answer this system gave
        yesterday, which is a perfectly good answer. Silent is not the same as invisible,
        though — an empty `keywords` is logged, because it is a real cause of "memory does
        nothing" that otherwise looks identical to "there was nothing to recall".
        """
        if not keywords.strip():
            logger.info("memory_recall_skipped", reason="no_keywords")
            return []

        try:
            memories = await self.repo.search(knowledge_base_id, keywords, self.max_injected)
        except Exception:  # noqa: BLE001
            logger.warning("memory_recall_failed")
            return []

        kept = self._within_budget(memories)

        # Recall is what "used" means. Previously `last_used_at` moved only when a fact was
        # re-derived by the distiller, so a memory injected into a hundred answers still
        # displayed as never used — the Memory page's staleness column was measuring the
        # wrong event entirely. Best-effort: failing to record the use must not cost the use.
        if kept:
            try:
                await self.repo.touch([memory.id for memory in kept])
            except Exception:  # noqa: BLE001
                logger.warning("memory_touch_failed", count=len(kept))

        logger.info("memory_recalled", found=len(memories), injected=len(kept))
        return kept

    def _within_budget(self, memories: list[Memory]) -> list[Memory]:
        """Drop the lowest-ranked memories until they fit.

        Memory has its own budget, subtracted from the assembler's at the composition seam,
        so turning it on cannot push a previously-fitting answer over the context limit. The
        same character-per-token estimate the assembler uses, so the two are comparable.
        """
        from src.application.chat.agentic.context import _CHARS_PER_TOKEN

        kept: list[Memory] = []
        spent = 0
        for memory in memories:
            cost = len(memory.content) / _CHARS_PER_TOKEN
            if spent + cost > self.token_budget:
                # `continue`, not `break`. Memories arrive best-first, so stopping at the
                # first one that does not fit throws away every better-than-nothing fact
                # behind a single long one. `memory_max_chars` bounds each at ~86 tokens, so
                # skipping one and taking the next is a real gain, not a rounding error.
                continue
            kept.append(memory)
            spent += cost
        return kept

    async def distil(
        self,
        knowledge_base_id: UUID,
        *,
        question: str,
        answer: str,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> list[Memory]:
        """Extract anything durable from one exchange and store it. Returns what was stored.

        Note what is *not* passed in: the retrieved context. See this module's docstring —
        that omission is the main defence against a poisoned document earning permanent
        residence in every future prompt.
        """
        existing = await self.repo.list_active(knowledge_base_id)

        try:
            distilled = await self._extract(question, answer, existing)
        except Exception:  # noqa: BLE001 - a malformed structured output is not worth a retry
            logger.warning("memory_distillation_failed")
            return []

        written: list[Memory] = []
        # Capped after the model returns, not asked for in the prompt. A model that ignores
        # an instruction is the normal case; a hard slice is not ignorable.
        for candidate in distilled.facts[: self.max_per_call]:
            content = candidate.content.strip()[: self.max_chars]
            if not content:
                continue

            duplicate = self._duplicate_of(content, existing)
            if duplicate is not None:
                # Already known. Bump it rather than storing the same fact twice in slightly
                # different words, which is how a memory list becomes unreadable.
                await self.repo.touch([duplicate.id])
                continue

            memory = await self.repo.create(
                Memory(
                    knowledge_base_id=knowledge_base_id,
                    content=content,
                    kind=(
                        MemoryKind.PREFERENCE
                        if candidate.kind == MemoryKind.PREFERENCE.value
                        else MemoryKind.FACT
                    ),
                    source_conversation_id=conversation_id,
                    source_message_id=message_id,
                )
            )
            written.append(memory)

            # No contradiction classifier: the model names what it replaces, in the same
            # call that produced the replacement. When it does not, both memories survive
            # and are injected together and the answering model hedges — which is the
            # honest failure, and better than silently picking one.
            if candidate.supersedes is not None and 1 <= candidate.supersedes <= len(existing):
                await self.repo.supersede(existing[candidate.supersedes - 1].id, memory.id)

        logger.info("memory_distilled", written=len(written), considered=len(distilled.facts))
        return written

    def _duplicate_of(self, content: str, existing: list[Memory]) -> Memory | None:
        for memory in existing:
            if similarity(content, memory.content) >= self.duplicate_threshold:
                return memory
        return None

    async def _extract(self, question: str, answer: str, existing: list[Memory]) -> _Distilled:
        listing = "\n".join(
            f"{i + 1}. {memory.content}" for i, memory in enumerate(existing)
        ) or "(none)"

        structured = self.llm.with_structured_output(_Distilled)
        return await structured.ainvoke(
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": _USER.format(
                        memories=listing, question=question, answer=answer[:4000]
                    ),
                },
            ]
        )
