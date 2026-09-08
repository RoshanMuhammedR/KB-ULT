"""Memory has to actually reach an answer, and the ways it silently did not.

The feature shipped in a state where every visible part worked and the invisible part did
nothing: the Memory page saved facts, listed them and deleted them, while not one of them was
ever injected into a prompt. Four separate causes stacked, and none of them raised, logged, or
failed a test. Each is pinned here.

The live database made the diagnosis: one row, `"my name is roshan"`, added by hand through
the UI, with `last_used_at` still NULL after weeks of use.
"""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from uuid import uuid4

from src.application.memory.service import MemoryService
from src.domain.entities import Memory, MemoryKind


class _FakeRepo:
    def __init__(self, memories=None, *, fail_search=False) -> None:
        self.memories = memories or []
        self.fail_search = fail_search
        self.searched: list[str] = []
        self.touched: list = []

    async def search(self, _kb, query, limit):
        if self.fail_search:
            raise RuntimeError("connection reset")
        self.searched.append(query)
        return self.memories[:limit]

    async def touch(self, ids):
        self.touched.extend(ids)

    async def list_active(self, _kb):
        return self.memories


def _memory(content: str) -> Memory:
    return Memory(knowledge_base_id=uuid4(), content=content, kind=MemoryKind.FACT)


def _service(repo, **overrides) -> MemoryService:
    settings = {
        "max_injected": 5,
        "max_chars": 300,
        "max_per_call": 3,
        "duplicate_threshold": 0.8,
        "token_budget": 400,
    }
    settings.update(overrides)
    return MemoryService(SimpleNamespace(), repo, **settings)


class RecallMarksUseTest(IsolatedAsyncioTestCase):
    async def test_recalling_a_memory_marks_it_used(self) -> None:
        """`last_used_at` has to mean "was put in front of a question".

        It previously moved only when the distiller re-derived an identical fact, so a memory
        injected into a hundred answers still displayed as never used. The Memory page's
        staleness column was measuring a different event than the one it named.
        """
        memories = [_memory("The team ships on Thursdays")]
        repo = _FakeRepo(memories)

        kept = await _service(repo).recall(uuid4(), "when does the team ship")

        self.assertEqual(len(kept), 1)
        self.assertEqual(repo.touched, [memories[0].id])

    async def test_nothing_is_touched_when_nothing_is_recalled(self) -> None:
        repo = _FakeRepo([])

        await _service(repo).recall(uuid4(), "unrelated question")

        self.assertEqual(repo.touched, [])

    async def test_a_failed_touch_does_not_cost_the_recall(self) -> None:
        """Failing to record the use must not lose the use."""

        class _Broken(_FakeRepo):
            async def touch(self, ids):
                raise RuntimeError("write failed")

        repo = _Broken([_memory("The team ships on Thursdays")])

        kept = await _service(repo).recall(uuid4(), "when does the team ship")

        self.assertEqual(len(kept), 1)


class RecallGuardsTest(IsolatedAsyncioTestCase):
    async def test_empty_keywords_never_reach_the_repository(self) -> None:
        """`QueryResolver.keywords` defaults to "" when the model omits the field.

        Searching on it is a guaranteed empty result, and it used to be indistinguishable
        from "there was genuinely nothing to recall".
        """
        repo = _FakeRepo([_memory("The team ships on Thursdays")])

        kept = await _service(repo).recall(uuid4(), "   ")

        self.assertEqual(kept, [])
        self.assertEqual(repo.searched, [])

    async def test_an_unavailable_store_returns_no_memories_rather_than_failing(self) -> None:
        repo = _FakeRepo(fail_search=True)

        self.assertEqual(await _service(repo).recall(uuid4(), "anything"), [])


class BudgetTest(IsolatedAsyncioTestCase):
    async def test_one_oversized_memory_does_not_discard_the_rest(self) -> None:
        """The budget skips what does not fit; it does not stop at it.

        Memories arrive best-first, so `break` threw away every remaining fact behind a single
        long one. Each is capped at `memory_max_chars` (~86 tokens), so continuing past one is
        a real gain rather than a rounding error.
        """
        repo = _FakeRepo([_memory("y" * 1200), _memory("short and useful")])

        kept = await _service(repo, token_budget=200).recall(uuid4(), "useful")

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].content, "short and useful")


class DistillGateTest(TestCase):
    """The gate fired on turn 1 of every conversation and then never again.

    `_maybe_distil` was passed `len(history)`, and history comes from
    `recent_messages(conversation_id, _HISTORY_TURNS=4)` — a message count hard-capped at 4.
    So the value went 0, 2, 4, 4, 4… forever, and `% 3 == 0` was true only at 0. The name said
    "every three turns"; the behaviour was "once, at the start, when there is least to learn".

    Reproduced here as the arithmetic, because the fix is the arithmetic.
    """

    @staticmethod
    def _old_gate(turn: int, every: int = 3) -> bool:
        # What the code did: length of a window capped at 4 messages, 2 per completed turn.
        history_length = min(4, (turn - 1) * 2)
        return history_length % every == 0

    @staticmethod
    def _new_gate(turn: int, every: int = 3) -> bool:
        return turn == 1 or turn % every == 0

    def test_the_old_gate_fired_once_and_never_again(self) -> None:
        fired = [turn for turn in range(1, 21) if self._old_gate(turn)]

        self.assertEqual(fired, [1], "the old gate only ever fired on the opening turn")

    def test_the_new_gate_fires_on_the_opening_turn_and_then_periodically(self) -> None:
        fired = [turn for turn in range(1, 21) if self._new_gate(turn)]

        self.assertEqual(fired, [1, 3, 6, 9, 12, 15, 18])

    def test_the_opening_turn_still_distils(self) -> None:
        """It is where people say who they are and how they want to be answered."""
        self.assertTrue(self._new_gate(1))


if __name__ == "__main__":
    import unittest

    unittest.main()
