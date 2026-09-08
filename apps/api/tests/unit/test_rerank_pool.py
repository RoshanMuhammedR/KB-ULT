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

    async def test_pool_preserves_fusion_order(self):
        """The list arrives fused; the pool is its head.

        This test previously asserted the opposite — that the pool was re-sorted by `SCORE`
        — which is the defect it was written to protect. `EnsembleRetriever` returns
        documents already ordered by `Σ weight / (rank + c)` and never writes that score to
        metadata, so position is the only record of fusion and `SCORE` is just raw cosine.
        Re-sorting looked like a safety net and was actually the bug.
        """
        recorder = {}
        docs = list(reversed(_docs(30)))  # ascending cosine: fusion order != SCORE order
        await _build(recorder).compress(docs, "q")

        # "29" leads the fused list and carries the *lowest* cosine. Under the old sort it
        # was dropped from the pool entirely; under fusion order it is scored first.
        self.assertIn("[0] 29", recorder["prompt"])
        # And the document with the best cosine but the worst fusion rank stays out.
        self.assertNotIn("[11] 0", recorder["prompt"])

    async def test_a_lexical_only_hit_reaches_the_pool(self):
        """The case the defect made unreachable, and the reason the lexical arm exists.

        An exact-identifier match is often a poor embedding neighbour: the lexical arm ranks
        it first, so RRF places it high, but its cosine is near the bottom. Sorting the pool
        by cosine meant that whenever the dense arm returned `candidate_limit` documents —
        which it does on any non-trivial corpus — such a hit could never be judged.
        """
        recorder = {}
        # Fused first by RRF, last by cosine: found brilliantly by one arm only.
        lexical_only = Document(
            page_content="ERR_CONN_REFUSED" + "x" * 5000, metadata={SCORE: 0.01}
        )
        await _build(recorder).compress([lexical_only, *_docs(30)], "q")

        self.assertIn("ERR_CONN_REFUSED", recorder["prompt"])

    async def test_each_document_is_truncated_for_scoring(self):
        recorder = {}
        await _build(recorder).compress(_docs(30), "q")

        # 12 excerpts, each capped - far below the 12 x 5000 chars the documents hold.
        self.assertLess(len(recorder["prompt"]), 12 * (_SCORE_EXCERPT_CHARS + 200))

    async def test_degraded_path_still_ranks_over_everything_retrieved(self):
        recorder = {}
        # Reversed so fusion order and cosine order disagree: passing this by accident is
        # not possible.
        documents = list(reversed(_docs(30)))
        kept, degraded = await _build(recorder, fail=True).compress(documents, "q")

        self.assertTrue(degraded)
        # The fallback keeps top_n // 2, chosen from the full retrieved set - the pool cut is
        # only about what the LLM sees, and must not narrow what degradation can fall back on.
        self.assertEqual(len(kept), 3)
        # Fusion order, not cosine order. With no judge, fusion rank is the only signal
        # left, so this is where discarding it would hurt most.
        self.assertEqual(kept, documents[:3])

    async def test_empty_input_short_circuits(self):
        recorder = {}
        kept, degraded = await _build(recorder).compress([], "q")

        self.assertEqual(kept, [])
        self.assertFalse(degraded)
        self.assertNotIn("prompt", recorder)



class DegradedFloorTests(unittest.IsolatedAsyncioTestCase):
    """A degraded rerank still has to filter something.

    `_passes` is only reachable on the success path, so a timeout previously let through
    whatever survived a positional cut — unjudged and unfiltered. Worse, `max(1, ...)`
    guaranteed at least one survivor, which makes `state.found_anything` unconditionally true
    and the deterministic "I could not find this" fallback unreachable: one provider blip
    turned an out-of-corpus question into a generated answer over arbitrary passages.

    A full eval run showed `rerank_degraded` on *every hop*, so this was not a rare edge — the
    relevance floor had never once been applied in production.
    """

    async def test_weak_documents_are_dropped_when_the_judge_is_unreachable(self):
        recorder = {}
        strong = Document(page_content="relevant" + "x" * 100, metadata={SCORE: 0.8})
        weak = Document(page_content="barely related" + "x" * 100, metadata={SCORE: 0.05})
        reranker = ScoringReranker(
            _LLM(recorder, fail=True),
            top_n=6,
            candidate_limit=12,
            threshold=0.35,
            asr_threshold=0.25,
            timeout_seconds=5,
            fusion_floor=0.25,
        )

        kept, degraded = await reranker.compress([strong, weak], "q")

        self.assertTrue(degraded)
        self.assertEqual(kept, [strong])

    async def test_everything_below_the_floor_leaves_nothing(self):
        """So `found_anything` can be false and the honest fallback becomes reachable."""
        recorder = {}
        weak = [Document(page_content="x" * 100, metadata={SCORE: 0.05}) for _ in range(4)]
        reranker = ScoringReranker(
            _LLM(recorder, fail=True),
            top_n=6,
            candidate_limit=12,
            threshold=0.35,
            asr_threshold=0.25,
            timeout_seconds=5,
            fusion_floor=0.25,
        )

        kept, degraded = await reranker.compress(weak, "q")

        self.assertTrue(degraded)
        self.assertEqual(kept, [])


if __name__ == "__main__":
    unittest.main()
