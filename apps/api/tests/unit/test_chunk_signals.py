"""The counters behind the learned relevance prior, and the two ways they go wrong.

**Drift.** A vote is a state, not an event. If a change of mind recorded only the new verdict,
a passage would accumulate both an upvote and a downvote from one person who simply changed
their mind, and the drift would compound with every further change. `vote_deltas` is the
arithmetic that prevents that, and the property worth pinning is that any journey back to a
previous state restores the counters exactly.

**Tenancy.** `record` and `apply_feedback` are the only writes in this codebase that use a
Core `insert()` rather than the ORM, which is what buys the single-round-trip upsert — and
what costs them the `before_flush` listener that stamps `tenant_id` everywhere else. A
regression there does not raise: it writes a row that no policy constrains, or NULL into a
NOT NULL column. So it is asserted directly.
"""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from uuid import uuid4

from src.core.tenant_context import reset_tenant_context, set_tenant_context
from src.domain.entities import ChunkSignalEvent
from src.infrastructure.repositories.postgres_chunk_signal_repository import (
    ChunkSignalRepository,
    vote_deltas,
)

_TENANT = uuid4()
_USER = uuid4()


class _FakeSession:
    """Captures executed Core statements without touching a database."""

    def __init__(self) -> None:
        self.executed: list = []
        self.committed = False
        self.info: dict = {}

    async def execute(self, statement):
        self.executed.append(statement)
        return SimpleNamespace(all=list, first=lambda: None)

    async def commit(self) -> None:
        self.committed = True

    async def flush(self) -> None:  # pragma: no cover
        pass

    def in_transaction(self) -> bool:
        return False

    async def scalars(self, _statement):
        raise AssertionError("no ORM query expected on the write path")


class VoteDeltaTests(TestCase):
    def test_a_first_vote_moves_one_counter(self) -> None:
        self.assertEqual(vote_deltas(None, 1), (1, 0))
        self.assertEqual(vote_deltas(None, -1), (0, 1))

    def test_changing_your_mind_undoes_the_old_vote_as_it_records_the_new(self) -> None:
        # The whole point: +1 down AND -1 up, not just +1 down.
        self.assertEqual(vote_deltas(1, -1), (-1, 1))
        self.assertEqual(vote_deltas(-1, 1), (1, -1))

    def test_retracting_removes_exactly_what_was_added(self) -> None:
        self.assertEqual(vote_deltas(1, None), (-1, 0))
        self.assertEqual(vote_deltas(-1, None), (0, -1))

    def test_repeating_the_same_verdict_moves_nothing(self) -> None:
        self.assertEqual(vote_deltas(1, 1), (0, 0))
        self.assertEqual(vote_deltas(-1, -1), (0, 0))
        self.assertEqual(vote_deltas(None, None), (0, 0))

    def test_up_then_down_then_retracted_returns_to_zero(self) -> None:
        """The regression that matters, walked as an actual journey.

        Any sequence of verdicts ending back at "no opinion" must leave a passage exactly
        where it started, or the counters slowly fill with the history of people's
        indecision rather than their conclusions.
        """
        up = down = 0
        for previous, current in [(None, 1), (1, -1), (-1, 1), (1, None)]:
            du, dd = vote_deltas(previous, current)
            up += du
            down += dd

        self.assertEqual((up, down), (0, 0))


class TenancyTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.token = set_tenant_context(_TENANT, _USER)

    def tearDown(self) -> None:
        reset_tenant_context(self.token)

    async def test_record_stamps_the_tenant_by_hand(self) -> None:
        """`before_flush` never sees a Core insert, so this has to be explicit."""
        session = _FakeSession()
        chunk_id = uuid4()

        await ChunkSignalRepository(session).record(
            [ChunkSignalEvent(chunk_id=chunk_id, cited=1, supported=1)]
        )

        compiled = str(session.executed[0].compile())
        self.assertIn("tenant_id", compiled)
        self.assertIn("user_id", compiled)
        params = session.executed[0].compile().params
        self.assertEqual(params["tenant_id_m0"], _TENANT)
        self.assertEqual(params["user_id_m0"], _USER)

    async def test_the_conflict_target_includes_the_tenant(self) -> None:
        """So a row carrying the wrong tenant collides with nothing instead of merging."""
        session = _FakeSession()
        await ChunkSignalRepository(session).record([ChunkSignalEvent(chunk_id=uuid4(), cited=1)])

        self.assertIn("ON CONFLICT (tenant_id, chunk_id)", str(session.executed[0].compile()))

    async def test_counters_accumulate_rather_than_overwrite(self) -> None:
        """`DO UPDATE SET cited = existing + excluded`, not `= excluded`."""
        session = _FakeSession()
        await ChunkSignalRepository(session).record([ChunkSignalEvent(chunk_id=uuid4(), cited=1)])

        compiled = str(session.executed[0].compile())
        self.assertIn("cited = (chunk_signals.cited + excluded.cited)", compiled)

    async def test_a_batch_without_a_citation_still_records_its_other_counters(self) -> None:
        """The bug a `where=` on the upsert would have introduced.

        `on_conflict_do_update(where=...)` gates the *entire* UPDATE, so using it to protect
        `last_cited_at` would have silently dropped `supported` and `unsupported` for any
        batch that recorded no citation. COALESCE scopes the protection to one column.
        """
        session = _FakeSession()
        await ChunkSignalRepository(session).record(
            [ChunkSignalEvent(chunk_id=uuid4(), cited=0, unsupported=1)]
        )

        compiled = str(session.executed[0].compile())
        self.assertIn("unsupported = (chunk_signals.unsupported + excluded.unsupported)", compiled)
        self.assertIn("coalesce(excluded.last_cited_at, chunk_signals.last_cited_at)", compiled)
        self.assertNotIn("WHERE", compiled.split("DO UPDATE")[1])

    async def test_nothing_is_written_for_an_empty_batch(self) -> None:
        session = _FakeSession()
        await ChunkSignalRepository(session).record([])

        self.assertEqual(session.executed, [])

    async def test_a_no_op_vote_change_issues_no_statement(self) -> None:
        session = _FakeSession()
        await ChunkSignalRepository(session).apply_feedback(
            [uuid4()], previous=1, current=1
        )

        self.assertEqual(session.executed, [])

    async def test_a_retraction_never_inserts_a_negative_count(self) -> None:
        """A retraction can land on a row that no longer exists — re-ingest deletes them.

        The INSERT half of the upsert must clamp at zero, or the row is created holding
        `upvoted = -1` and every prior computed from it is nonsense.
        """
        session = _FakeSession()
        await ChunkSignalRepository(session).apply_feedback(
            [uuid4()], previous=1, current=None
        )

        params = session.executed[0].compile().params
        self.assertEqual(params["upvoted_m0"], 0)
        self.assertEqual(params["downvoted_m0"], 0)
        # ...while the UPDATE half still applies the real decrement.
        self.assertIn("upvoted = (chunk_signals.upvoted + ", str(session.executed[0].compile()))


if __name__ == "__main__":
    import unittest

    unittest.main()
