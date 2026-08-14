from __future__ import annotations

from src.domain.entities import RetrievalResult


class PromptBuilder:
    def build(
        self,
        question: str,
        results: list[RetrievalResult],
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """`history` is the tail of the thread, so follow-ups read in context.

        It is passed as prior turns rather than folded into the question, so the model can
        tell what was asked before from what is being asked now.
        """
        context_blocks = []
        for index, result in enumerate(results, start=1):
            # Source-neutral position: for PDF the locator is a page, but the prompt
            # just labels it generically so non-file sources need no change here.
            locator = result.chunk.metadata.get("locator") or {}
            position = locator.get("value") if isinstance(locator, dict) else None
            source = result.chunk.metadata.get("filename")
            context_blocks.append(
                f"[{index}] source={source} at={position} score={result.score:.3f}\n{result.chunk.text}"
            )

        system_prompt = (
            "You answer questions only from the retrieved context. "
            "If the context does not contain the answer, say that the knowledge base "
            "does not contain enough information. Include concise citations using "
            "the bracket numbers from the context."
        )
        user_prompt = f"Question:\n{question}\n\nRetrieved context:\n\n" + "\n\n".join(context_blocks)
        return [
            {"role": "system", "content": system_prompt},
            *(history or []),
            {"role": "user", "content": user_prompt},
        ]

    def insufficient_context_answer(self) -> str:
        return "The knowledge base does not contain enough relevant context to answer this question."
