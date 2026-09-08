"""A compound question has to retrieve for every part of itself.

The measured failure: `multi_hop` recall 0.40 on the golden set while every other kind scored
1.0, and all five multi-hop cases exited `sufficient` at `hops=1`. Two independent defects
produced that, and fixing either alone would not have helped.

**The grader could not see the parts.** It was asked whether the passages answered "the
central question" — singular — and returned one boolean. For "which model, and which
gateway?", passages about the model do answer the central question, so it said yes. Its
`missing` field, which could have said otherwise, was recorded on the trace and read by
nothing.

**The rewrite discarded half the question.** `QueryRewriter._decompose` kept `parts[0]`, so
even a second hop would have re-searched the half hop 1 already had. Its docstring diagnosed
the problem exactly right and then did the wrong thing about it.
"""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from uuid import uuid4

from langchain_core.documents import Document

from src.application.chat.agentic.loop import LoopState, RetrievalLoop
from src.retrieval.langchain.query import QueryDecomposer, Sufficiency, SufficiencyChecker
from src.retrieval.langchain.retrievers import CHUNK_ID, SCORE

_COMPOUND = "Which AI model does the trip planner use, and which gateway does it call it through?"


class _Model:
    """Stands in for `llm.with_structured_output(...)`, returning a scripted object."""

    def __init__(self, result=None, *, fail=False) -> None:
        self.result = result
        self.fail = fail
        self.calls = 0
        self.prompts: list[str] = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        self.prompts.append(chr(10).join(m["content"] for m in messages))
        if self.fail:
            raise RuntimeError("gateway unreachable")
        return self.result


class DecompositionTest(IsolatedAsyncioTestCase):
    async def test_a_simple_question_costs_no_model_call(self) -> None:
        """The common case must not pay for the uncommon one."""
        model = _Model()

        parts = await QueryDecomposer(model).decompose("What is the notice period?")

        self.assertEqual(parts, ["What is the notice period?"])
        self.assertEqual(model.calls, 0)

    async def test_a_compound_question_is_split(self) -> None:
        model = _Model(
            SimpleNamespace(
                parts=[
                    "Which AI model does the trip planner use?",
                    "Which gateway does the trip planner call the AI model through?",
                ]
            )
        )

        parts = await QueryDecomposer(model).decompose(_COMPOUND)

        self.assertEqual(len(parts), 2)
        self.assertIn("gateway", parts[1])

    async def test_each_part_must_stand_alone(self) -> None:
        """The prompt has to demand it, because a part containing "it" retrieves nothing."""
        model = _Model(SimpleNamespace(parts=["a", "b"]))

        await QueryDecomposer(model).decompose(_COMPOUND)

        self.assertIn("stand alone", model.prompts[0])

    async def test_more_parts_than_allowed_are_cut(self) -> None:
        model = _Model(SimpleNamespace(parts=[f"part {i}" for i in range(9)]))

        parts = await QueryDecomposer(model).decompose(_COMPOUND)

        self.assertEqual(len(parts), 3)

    async def test_a_failed_split_falls_back_to_the_whole_question(self) -> None:
        """One combined retrieval is what this system did before. A raised exception is no
        answer at all."""
        parts = await QueryDecomposer(_Model(fail=True)).decompose(_COMPOUND)

        self.assertEqual(parts, [_COMPOUND])

    async def test_an_empty_split_falls_back_too(self) -> None:
        model = _Model(SimpleNamespace(parts=["", "   "]))

        self.assertEqual(await QueryDecomposer(model).decompose(_COMPOUND), [_COMPOUND])

    def test_the_pre_check_catches_the_real_golden_cases(self) -> None:
        """Every multi-hop case in the golden set joins its halves with ", and "."""
        self.assertTrue(QueryDecomposer.looks_compound(_COMPOUND))
        self.assertTrue(
            QueryDecomposer.looks_compound("How is a user authenticated, and what stops edits?")
        )
        self.assertFalse(QueryDecomposer.looks_compound("What is the notice period?"))


class SufficiencyPerPartTest(IsolatedAsyncioTestCase):
    async def test_the_judge_is_shown_the_parts_numbered(self) -> None:
        model = _Model(Sufficiency(sufficient=True))
        checker = SufficiencyChecker(model, min_chunks=1)

        await checker.check(_COMPOUND, ["a passage", "another"], ["first part", "second part"])

        prompt = model.prompts[0]
        self.assertIn("1. first part", prompt)
        self.assertIn("2. second part", prompt)

    async def test_an_uncovered_part_overrides_a_positive_verdict(self) -> None:
        """A model can say "sufficient" and still name an unanswered part. Believe the list:
        it is the specific claim and the boolean is only its summary."""
        model = _Model(Sufficiency(sufficient=True, uncovered_parts=[2]))
        checker = SufficiencyChecker(model, min_chunks=1)

        verdict = await checker.check(_COMPOUND, ["a", "b"], ["first", "second"])

        self.assertFalse(verdict.sufficient)

    async def test_a_single_part_question_is_judged_as_before(self) -> None:
        model = _Model(Sufficiency(sufficient=True))
        checker = SufficiencyChecker(model, min_chunks=1)

        await checker.check("What is the notice period?", ["a", "b"], ["What is the notice period?"])

        self.assertNotIn("Parts that must each be answered", model.prompts[0])

    async def test_an_unreachable_grader_is_marked_degraded(self) -> None:
        """It still fails open — a provider blip must not become "I don't know" — but the
        trace has to be able to tell approval apart from an outage."""
        checker = SufficiencyChecker(_Model(fail=True), min_chunks=1)

        verdict = await checker.check("q", ["a", "b"], ["q"])

        self.assertTrue(verdict.sufficient)
        self.assertTrue(verdict.degraded)


def _document(chunk_id: str, text: str) -> Document:
    return Document(page_content=text, metadata={CHUNK_ID: chunk_id, SCORE: 0.9})


class _Reranker:
    async def compress(self, documents, query):
        return documents, False


class _Rewriter:
    async def rewrite(self, query):
        return f"rewritten {query}", "broaden"


class _PerPartStore:
    """Returns a different passage for each sub-question, and nothing for the whole.

    That is the shape of the real failure: one embedding over two subjects lands between them
    and matches neither well, while each half retrieves cleanly on its own.
    """

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search_dense(self, embedding, kb_id, limit, threshold):
        return []

    async def search_lexical(self, embedding, query, kb_id, limit):
        return []


class LoopRetrievesPerPartTest(IsolatedAsyncioTestCase):
    def _loop(self, fetched: dict[str, list[Document]], verdicts):
        seen: list[str] = []

        class _Loop(RetrievalLoop):
            async def _fetch(self, query, lexical_query, knowledge_base_id):
                seen.append(query)
                return fetched.get(query, [])

        loop = _Loop(
            vector_store=None,
            embedding_provider=None,
            reranker=_Reranker(),
            rewriter=_Rewriter(),
            sufficiency=verdicts,
            max_hops=2,
            candidate_limit=30,
            threshold=0.0,
            rrf_k=60,
        )
        return loop, seen

    async def test_each_part_gets_its_own_retrieval(self) -> None:
        """The whole point. One retrieval over a two-subject question found neither."""

        class _Verdict:
            async def check(self, question, passages, parts=None):
                return Sufficiency(sufficient=True)

        fetched = {
            "Which model?": [_document("model-chunk", "It uses Gemini")],
            "Which gateway?": [_document("gateway-chunk", "It calls AICredits")],
        }
        loop, seen = self._loop(fetched, _Verdict())
        state = LoopState(
            question=_COMPOUND,
            resolved_query=_COMPOUND,
            parts=["Which model?", "Which gateway?"],
        )

        async for _ in loop.stream(state, uuid4()):
            pass

        self.assertEqual(seen, ["Which model?", "Which gateway?"])
        found = {d.metadata[CHUNK_ID] for d in state.documents}
        self.assertEqual(found, {"model-chunk", "gateway-chunk"})

    async def test_the_second_hop_searches_what_was_missing(self) -> None:
        """Not a rewrite of the whole question. `_decompose` used to keep the first clause,
        so hop 2 re-searched the half hop 1 already had."""

        class _Verdict:
            def __init__(self):
                self.calls = 0

            async def check(self, question, passages, parts=None):
                self.calls += 1
                if self.calls == 1:
                    return Sufficiency(sufficient=False, uncovered_parts=[2])
                return Sufficiency(sufficient=True)

        fetched = {"Which model?": [_document("model-chunk", "Gemini")]}
        loop, seen = self._loop(fetched, _Verdict())
        state = LoopState(
            question=_COMPOUND,
            resolved_query=_COMPOUND,
            parts=["Which model?", "Which gateway?"],
        )

        async for _ in loop.stream(state, uuid4()):
            pass

        # Hop 1 searched both parts; hop 2 searched only the uncovered one.
        self.assertEqual(seen, ["Which model?", "Which gateway?", "Which gateway?"])

    async def test_a_half_answered_question_is_not_complete(self) -> None:
        """`complete` gates INCOMPLETE_CONTEXT_RULE — the one instruction that makes the
        model admit a gap. It used to be `exit_reason == "sufficient"`, which was true on
        every half-answered multi-hop question in the golden set."""

        class _Verdict:
            async def check(self, question, passages, parts=None):
                return Sufficiency(sufficient=False, uncovered_parts=[2])

        fetched = {"Which model?": [_document("model-chunk", "Gemini")]}
        loop, _seen = self._loop(fetched, _Verdict())
        state = LoopState(
            question=_COMPOUND,
            resolved_query=_COMPOUND,
            parts=["Which model?", "Which gateway?"],
        )

        async for _ in loop.stream(state, uuid4()):
            pass

        self.assertEqual(state.uncovered_parts, ["Which gateway?"])
        self.assertFalse(state.complete)

    async def test_a_covered_question_is_complete(self) -> None:
        class _Verdict:
            async def check(self, question, passages, parts=None):
                return Sufficiency(sufficient=True)

        fetched = {"q": [_document("c", "text")]}
        loop, _seen = self._loop(fetched, _Verdict())
        state = LoopState(question="q", resolved_query="q", parts=["q"])

        async for _ in loop.stream(state, uuid4()):
            pass

        self.assertTrue(state.complete)


class TraceTest(TestCase):
    def test_the_trace_carries_the_parts_and_what_was_missed(self) -> None:
        state = LoopState(
            question="q",
            resolved_query="q",
            parts=["a", "b"],
            uncovered_parts=["b"],
            exit_reason="max_hops",
        )

        wire = state.to_wire()

        self.assertEqual(wire["parts"], ["a", "b"])
        self.assertEqual(wire["uncovered_parts"], ["b"])
        self.assertIn("grader_degraded", wire)


if __name__ == "__main__":
    import unittest

    unittest.main()


class SiblingChildrenTest(IsolatedAsyncioTestCase):
    """Two children of one section are one citation and two passages.

    Collapsing them to a single citation is right for the reader. Dropping the sibling
    entirely was not: it was invisible to the eval's recall — so a multi-hop case whose two
    expected chunks shared a section was capped at 0.5 however well retrieval had done — and
    invisible to `_record_signals`, so the learned prior never learned from it.
    """

    async def test_both_matched_children_survive_as_one_citation(self) -> None:
        from src.application.chat.agentic.context import ContextAssembler
        from src.domain.entities import Chunk
        from src.retrieval.langchain.retrievers import PARENT_ID

        parent_id = uuid4()
        parent = Chunk(id=parent_id, text="The whole section, both halves of it.")

        class _Repo:
            async def list_parents(self, ids):
                return {parent_id: parent}

        siblings = [
            Document(
                page_content="first half",
                metadata={CHUNK_ID: "child-a", PARENT_ID: str(parent_id), SCORE: 0.9},
            ),
            Document(
                page_content="second half",
                metadata={CHUNK_ID: "child-b", PARENT_ID: str(parent_id), SCORE: 0.8},
            ),
        ]

        assembled = await ContextAssembler(_Repo(), token_budget=8000).assemble(siblings)

        # One citation for the reader...
        self.assertEqual(len(assembled.citations), 1)
        # ...and both passages still accounted for.
        self.assertEqual(
            sorted(assembled.citations[0].matched_chunk_ids), ["child-a", "child-b"]
        )
        self.assertEqual(
            sorted(assembled.wire_citations[0]["matched_chunk_ids"]), ["child-a", "child-b"]
        )

    async def test_an_unexpanded_document_still_reports_its_own_id(self) -> None:
        from src.application.chat.agentic.context import ContextAssembler

        class _Repo:
            async def list_parents(self, ids):
                return {}

        lone = [Document(page_content="text", metadata={CHUNK_ID: "solo", SCORE: 0.9})]

        assembled = await ContextAssembler(_Repo(), token_budget=8000).assemble(lone)

        self.assertEqual(assembled.citations[0].matched_chunk_ids, ["solo"])
