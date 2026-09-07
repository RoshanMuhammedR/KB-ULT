"""Memory is the highest-value injection target in the system, so its limits are tested.

A retrieved passage influences one answer. A memory is injected into *every* future prompt in
the workspace, against questions that have nothing to do with where it came from. That
asymmetry is why the distiller never sees the retrieved context, and why the length and count
limits live in code rather than in the prompt — a model that ignores "at most three facts" is
the normal case, not a bug worth retrying.

The other thing pinned here is the memory block's precedence rule. Memories are older than the
corpus and unsourced; the documents are the ground truth this product promises.
"""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from uuid import uuid4

from src.application.chat.agentic.prompts import build_messages
from src.application.memory.service import MemoryService, similarity
from src.domain.entities import Memory, MemoryKind


class _FakeLLM:
    """Returns a fixed `_Distilled`, and records the prompt it was given."""

    def __init__(self, facts: list[dict]) -> None:
        self.facts = facts
        self.prompt = ""

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    async def ainvoke(self, messages):
        self.prompt = "\n".join(m["content"] for m in messages)
        from src.application.memory.service import _Candidate, _Distilled

        return _Distilled(facts=[_Candidate(**fact) for fact in self.facts])


class _FakeRepo:
    def __init__(self, existing: list[Memory] | None = None) -> None:
        self.existing = existing or []
        self.created: list[Memory] = []
        self.touched: list = []
        self.superseded: list[tuple] = []

    async def list_active(self, _kb):
        return self.existing

    async def search(self, _kb, _query, limit):
        return self.existing[:limit]

    async def create(self, memory):
        self.created.append(memory)
        return memory

    async def touch(self, ids):
        self.touched.extend(ids)

    async def supersede(self, old_id, new_id):
        self.superseded.append((old_id, new_id))


def _service(llm, repo, **overrides) -> MemoryService:
    settings = {
        "max_injected": 5,
        "max_chars": 300,
        "max_per_call": 3,
        "duplicate_threshold": 0.8,
        "token_budget": 400,
    }
    settings.update(overrides)
    return MemoryService(llm, repo, **settings)


def _memory(content: str) -> Memory:
    return Memory(knowledge_base_id=uuid4(), content=content, kind=MemoryKind.FACT)


class DistillationLimitsTest(IsolatedAsyncioTestCase):
    async def test_the_distiller_never_sees_the_retrieved_context(self) -> None:
        """The defence that matters, asserted at the call boundary.

        `distil` takes no context parameter at all, so a poisoned document cannot reach the
        prompt that decides what gets remembered forever. This test exists to make that a
        deliberate contract rather than an accident of the current signature — adding a
        `context=` argument to make some future thing work would break it here first.
        """
        llm = _FakeLLM([])
        repo = _FakeRepo()

        await _service(llm, repo).distil(
            uuid4(), question="What is the notice period?", answer="Thirty days."
        )

        self.assertIn("Thirty days", llm.prompt)
        self.assertIn("notice period", llm.prompt)
        # Nothing resembling a document block reached it.
        self.assertNotIn("<document>", llm.prompt)

    async def test_more_facts_than_allowed_are_cut_after_the_model_returns(self) -> None:
        """A model that ignores an instruction is the normal case; a slice is not ignorable."""
        llm = _FakeLLM([{"content": f"Fact number {i} about something"} for i in range(10)])
        repo = _FakeRepo()

        await _service(llm, repo, max_per_call=3).distil(
            uuid4(), question="q", answer="a"
        )

        self.assertEqual(len(repo.created), 3)

    async def test_an_overlong_fact_is_truncated_not_rejected(self) -> None:
        """Length is a cost paid in every future prompt, forever."""
        llm = _FakeLLM([{"content": "x" * 5000}])
        repo = _FakeRepo()

        await _service(llm, repo, max_chars=300).distil(uuid4(), question="q", answer="a")

        self.assertEqual(len(repo.created[0].content), 300)

    async def test_a_malformed_response_writes_nothing_and_does_not_raise(self) -> None:
        """Distillation runs in a worker with two attempts; a bad output is not worth one."""

        class _Broken:
            def with_structured_output(self, schema):
                return self

            async def ainvoke(self, messages):
                raise ValueError("not valid JSON")

        repo = _FakeRepo()
        written = await _service(_Broken(), repo).distil(uuid4(), question="q", answer="a")

        self.assertEqual(written, [])
        self.assertEqual(repo.created, [])

    async def test_a_restatement_bumps_the_existing_memory_instead_of_adding_one(self) -> None:
        existing = _memory("The team ships on Thursdays")
        llm = _FakeLLM([{"content": "The team ships on Thursdays"}])
        repo = _FakeRepo([existing])

        await _service(llm, repo).distil(uuid4(), question="q", answer="a")

        self.assertEqual(repo.created, [])
        self.assertEqual(repo.touched, [existing.id])

    async def test_a_contradiction_retires_what_it_replaces(self) -> None:
        """No classifier: the model names what it supersedes in the same call.

        When it does not, both survive and are injected together and the answering model
        hedges — the honest failure, and better than silently picking one.
        """
        existing = _memory("The team ships on Thursdays")
        llm = _FakeLLM([{"content": "The team now ships on Mondays", "supersedes": 1}])
        repo = _FakeRepo([existing])

        await _service(llm, repo).distil(uuid4(), question="q", answer="a")

        self.assertEqual(len(repo.created), 1)
        self.assertEqual(repo.superseded, [(existing.id, repo.created[0].id)])

    async def test_an_out_of_range_supersedes_index_is_ignored(self) -> None:
        """A hallucinated index refers to nothing; retiring an arbitrary memory would be worse
        than retiring none."""
        existing = _memory("The team ships on Thursdays")
        llm = _FakeLLM([{"content": "Something else entirely happens here", "supersedes": 7}])
        repo = _FakeRepo([existing])

        await _service(llm, repo).distil(uuid4(), question="q", answer="a")

        self.assertEqual(repo.superseded, [])


class RecallTest(IsolatedAsyncioTestCase):
    async def test_recall_stops_at_the_token_budget(self) -> None:
        """Memory has its own budget, subtracted from the assembler's at composition, so
        enabling it cannot push a previously-fitting answer over the context limit."""
        repo = _FakeRepo([_memory("y" * 700) for _ in range(5)])

        recalled = await _service(_FakeLLM([]), repo, token_budget=400).recall(uuid4(), "q")

        # 700 chars is 200 tokens at 3.5 chars/token, so exactly two fit in 400.
        self.assertEqual(len(recalled), 2)

    async def test_an_unavailable_store_returns_no_memories_rather_than_failing(self) -> None:
        """An answer without memory is the answer this system gave yesterday."""

        class _Broken(_FakeRepo):
            async def search(self, *args, **kwargs):
                raise RuntimeError("connection reset")

        recalled = await _service(_FakeLLM([]), _Broken()).recall(uuid4(), "q")

        self.assertEqual(recalled, [])


class SimilarityTest(TestCase):
    def test_a_restatement_scores_above_the_threshold(self) -> None:
        self.assertGreaterEqual(
            similarity("The team ships on Thursdays", "the team ships on thursdays"), 0.8
        )

    def test_two_different_facts_score_below_it(self) -> None:
        self.assertLess(
            similarity("The team ships on Thursdays", "Invoices are paid net thirty"), 0.8
        )

    def test_short_words_are_ignored_so_grammar_does_not_inflate_the_score(self) -> None:
        # Without the length filter, "the/on/is/of" would make every pair of sentences look
        # similar and unrelated facts would silently dedupe each other away.
        self.assertLess(similarity("the cat is on the mat", "the dog is on the log"), 0.5)

    def test_an_empty_memory_matches_nothing(self) -> None:
        self.assertEqual(similarity("", "anything at all"), 0.0)


class MemoryPromptTest(TestCase):
    def test_the_retrieved_context_is_declared_to_win(self) -> None:
        """The load-bearing clause. Memories are older and unsourced; documents are the
        ground truth the product promises."""
        messages = build_messages("q", ["block"], memories=["The team ships on Thursdays"])
        block = next(m["content"] for m in messages if "<memory>" in m["content"])

        self.assertIn("THE RETRIEVED CONTEXT IS CORRECT", block)
        self.assertIn("never cite them", block)

    def test_memories_are_not_part_of_the_numbered_context(self) -> None:
        """They must never become citations: there is no passage to verify against, no
        locator for the citation UI, and `find_by_cited_asset` would point at no asset."""
        messages = build_messages("q", ["[1] a real passage"], memories=["a remembered fact"])
        user_turn = messages[-1]["content"]

        self.assertIn("a real passage", user_turn)
        self.assertNotIn("a remembered fact", user_turn)

    def test_no_memory_block_is_added_when_there_are_none(self) -> None:
        with_none = build_messages("q", ["block"], memories=None)
        with_empty = build_messages("q", ["block"], memories=[])

        self.assertEqual(len(with_none), 2)
        self.assertEqual(len(with_empty), 2)


if __name__ == "__main__":
    import unittest

    unittest.main()
