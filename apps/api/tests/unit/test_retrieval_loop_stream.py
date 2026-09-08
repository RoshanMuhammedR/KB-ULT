import unittest
from uuid import uuid4

from langchain_core.documents import Document

from src.application.chat.agentic.loop import LoopState, RetrievalLoop
from src.retrieval.langchain.query import Sufficiency
from src.retrieval.langchain.retrievers import CHUNK_ID


def _doc(chunk_id: str, score: float = 1.0) -> Document:
    return Document(page_content=f"passage {chunk_id}", metadata={CHUNK_ID: chunk_id, "score": score})


class _Reranker:
    def __init__(self, degraded: bool = False):
        self.degraded = degraded

    async def compress(self, documents, query):
        return documents, self.degraded


class _Sufficiency:
    """Answers `sufficient` from a scripted list, one entry per hop.

    `parts` is accepted and recorded rather than ignored: the real checker is asked which
    numbered parts of a compound question went unanswered, and a fake that quietly dropped
    the argument would hide the loop failing to pass it.
    """

    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.seen_parts: list[list[str] | None] = []

    async def check(self, question, passages, parts=None):
        self.seen_parts.append(parts)
        sufficient = self.verdicts.pop(0) if self.verdicts else True
        return Sufficiency(sufficient=sufficient, missing="" if sufficient else "the pricing table")


class _Rewriter:
    async def rewrite(self, query):
        return f"{query} (broadened)", "broaden"


class _Loop(RetrievalLoop):
    """Overrides only retrieval, so the loop's control flow and event order are what is tested."""

    def __init__(self, pages, **kwargs):
        super().__init__(**kwargs)
        self.pages = list(pages)

    async def _fetch(self, query, lexical_query, knowledge_base_id):
        return self.pages.pop(0) if self.pages else []


def _build(pages, verdicts, *, degraded=False, max_hops=2) -> _Loop:
    return _Loop(
        pages,
        vector_store=None,
        embedding_provider=None,
        reranker=_Reranker(degraded),
        rewriter=_Rewriter(),
        sufficiency=_Sufficiency(verdicts),
        max_hops=max_hops,
        candidate_limit=30,
        threshold=0.0,
        rrf_k=60,
    )


class RetrievalLoopStreamTests(unittest.IsolatedAsyncioTestCase):
    """The loop must narrate itself.

    Reporting the whole multi-hop loop as one opaque "searching" left the user watching an
    unchanging label for the longest phase of answering a question. Each phase boundary now
    emits a frame, and `state` is still fully populated once the generator is drained.
    """

    async def test_single_hop_emits_each_phase_in_order(self):
        loop = _build(pages=[[_doc("a"), _doc("b")]], verdicts=[True])
        state = LoopState(question="q", resolved_query="q")

        stages = [payload["stage"] async for _, payload in loop.stream(state, uuid4())]

        self.assertEqual(stages, ["searching", "ranking", "grading"])
        self.assertEqual(state.exit_reason, "sufficient")
        self.assertEqual(state.hop_count, 1)

    async def test_insufficient_context_rewrites_and_runs_a_second_hop(self):
        loop = _build(pages=[[_doc("a")], [_doc("b")]], verdicts=[False, True])
        state = LoopState(question="q", resolved_query="q")

        frames = [(e, p) async for e, p in loop.stream(state, uuid4())]
        stages = [p["stage"] for _, p in frames]

        self.assertEqual(
            stages,
            ["searching", "ranking", "grading", "rewriting", "searching", "ranking", "grading"],
        )
        # The rewrite frame names the strategy, and the second hop counts itself.
        rewriting = next(p for _, p in frames if p["stage"] == "rewriting")
        self.assertEqual(rewriting["strategy"], "broaden")
        self.assertEqual(rewriting["hop"], 2)
        self.assertEqual([p["hop"] for _, p in frames if p["stage"] == "searching"], [1, 2])
        self.assertEqual(state.hop_count, 2)

    async def test_every_frame_is_a_status_event(self):
        loop = _build(pages=[[_doc("a")]], verdicts=[True])
        state = LoopState(question="q", resolved_query="q")

        events = {event async for event, _ in loop.stream(state, uuid4())}

        self.assertEqual(events, {"status"})

    async def test_ranking_frame_reports_the_candidate_count(self):
        loop = _build(pages=[[_doc("a"), _doc("b"), _doc("c")]], verdicts=[True])
        state = LoopState(question="q", resolved_query="q")

        frames = [p async for _, p in loop.stream(state, uuid4())]

        self.assertEqual(next(p for p in frames if p["stage"] == "ranking")["candidates"], 3)

    async def test_trace_survives_serialisation(self):
        loop = _build(pages=[[_doc("a")], [_doc("b")]], verdicts=[False, True])
        state = LoopState(question="q", resolved_query="resolved q")

        async for _ in loop.stream(state, uuid4()):
            pass
        wire = state.to_wire()

        self.assertEqual(wire["resolved_query"], "resolved q")
        self.assertEqual(wire["exit_reason"], "sufficient")
        self.assertEqual([hop["hop"] for hop in wire["hops"]], [1, 2])
        self.assertEqual(wire["hops"][0]["strategy"], "initial")
        self.assertEqual(wire["hops"][1]["strategy"], "broaden")
        self.assertEqual(wire["hops"][0]["missing"], "the pricing table")
        # The passages themselves are never in the trace - citations already carry them.
        self.assertNotIn("documents", wire)

    async def test_nothing_found_twice_stops_without_a_third_search(self):
        loop = _build(pages=[[], []], verdicts=[False, False], max_hops=5)
        state = LoopState(question="q", resolved_query="q")

        async for _ in loop.stream(state, uuid4()):
            pass

        self.assertEqual(state.exit_reason, "nothing_found")
        self.assertEqual(state.hop_count, 2)


if __name__ == "__main__":
    unittest.main()
