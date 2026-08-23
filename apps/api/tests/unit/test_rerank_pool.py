import unittest

from langchain_core.documents import Document

from src.retrieval.langchain.rerank import _SCORE_EXCERPT_CHARS, ScoringReranker
from src.retrieval.langchain.retrievers import SCORE


class _Structured:
    """Stands in for `llm.with_structured_output(_Ranking)`, recording what it was asked."""

    def __init__(self, recorder, fail=False):
        self.recorder = recorder
        self.fail = fail

    async def ainvoke(self, messages):
        self.recorder["prompt"] = messages[1]["content"]
        if self.fail:
            raise TimeoutError("provider took too long")

        from src.retrieval.langchain.rerank import _Ranking, _ScoredDocument

        # Every excerpt renders with a leading newline, the first one included.
        count = self.recorder["prompt"].count(chr(10) + "[")
        self.recorder["scored"] = count
        return _Ranking(scores=[_ScoredDocument(index=i, relevance=0.9) for i in range(count)])


class _LLM:
    def __init__(self, recorder, fail=False):
        self.recorder = recorder
        self.fail = fail

    def with_structured_output(self, schema):
        return _Structured(self.recorder, self.fail)


def _docs(n: int) -> list[Document]:
    # Descending fusion score, and long enough that truncation is observable.
    return [
        Document(page_content=f"{i}" + "x" * 5000, metadata={SCORE: 1.0 - i / 100})
        for i in range(n)
    ]


def _build(recorder, *, fail=False, candidate_limit=12) -> ScoringReranker:
    return ScoringReranker(
        _LLM(recorder, fail),
        top_n=6,
        candidate_limit=candidate_limit,
        threshold=0.35,
        asr_threshold=0.25,
        timeout_seconds=5,
    )


class RerankPoolTests(unittest.IsolatedAsyncioTestCase):
    """Only the strongest candidates are worth an LLM opinion.

    Scoring the whole over-fetched pool at full length built a prompt too large to finish
    inside the timeout, so every query paid the full wait and then discarded the result and
    fell back to fusion order with *half* the usual passages.
    """

    async def test_scores_only_the_candidate_limit(self):
        recorder = {}
        await _build(recorder).compress(_docs(30), "q")

        self.assertEqual(recorder["scored"], 12)

    async def test_scores_the_highest_fusion_scores_not_an_arbitrary_slice(self):
        recorder = {}
        docs = list(reversed(_docs(30)))  # weakest first, so order cannot be relied on
        await _build(recorder).compress(docs, "q")

        # Document "0" carries the top fusion score and must be in the scored pool.
        self.assertIn("[0] 0", recorder["prompt"])

    async def test_each_document_is_truncated_for_scoring(self):
        recorder = {}
        await _build(recorder).compress(_docs(30), "q")

        # 12 excerpts, each capped - far below the 12 x 5000 chars the documents hold.
        self.assertLess(len(recorder["prompt"]), 12 * (_SCORE_EXCERPT_CHARS + 200))

    async def test_degraded_path_still_ranks_over_everything_retrieved(self):
        recorder = {}
        documents = _docs(30)
        kept, degraded = await _build(recorder, fail=True).compress(documents, "q")

        self.assertTrue(degraded)
        # The fallback keeps top_n // 2, chosen from the full retrieved set - the pool cut is
        # only about what the LLM sees, and must not narrow what degradation can fall back on.
        self.assertEqual(len(kept), 3)
        self.assertEqual(kept[0].metadata[SCORE], max(d.metadata[SCORE] for d in documents))

    async def test_empty_input_short_circuits(self):
        recorder = {}
        kept, degraded = await _build(recorder).compress([], "q")

        self.assertEqual(kept, [])
        self.assertFalse(degraded)
        self.assertNotIn("prompt", recorder)


if __name__ == "__main__":
    unittest.main()
