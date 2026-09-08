"""What "no base named" means when listing threads.

It used to mean *the workspace default base*: the route resolved `None` to
`ensure_default()`, which is "the oldest row in the tenant". With one base that was
invisible. With several it hid every thread started anywhere else from a client that had not
picked a base yet — and after the UI moved to one thread list across every base, that client
is the only one there is.

So `None` now means the whole workspace, and this pins both halves of that: the route must
not substitute a base id, and the repository must not filter when given none.
"""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from uuid import uuid4

from src.infrastructure.repositories.postgres_conversation_repository import (
    ConversationRepository,
)


class _CapturingDb:
    """Records the statement it was asked to run, and returns nothing."""

    def __init__(self) -> None:
        self.statements: list[object] = []

    async def scalars(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(all=lambda: [])


class ConversationListingScopeTests(IsolatedAsyncioTestCase):
    async def test_no_base_does_not_filter_by_base(self) -> None:
        db = _CapturingDb()
        rows = await ConversationRepository(db).list_for_knowledge_base(None)

        self.assertEqual(rows, [])
        # The WHERE clause, not the whole statement: `knowledge_base_id` is a selected
        # column either way, so asserting on the compiled SQL would pass no matter what.
        self.assertIsNone(
            db.statements[0].whereclause,
            "listing every thread must not filter by base",
        )

    async def test_a_named_base_still_filters(self) -> None:
        db = _CapturingDb()
        await ConversationRepository(db).list_for_knowledge_base(uuid4())

        # The narrowing path has to keep working: /bases and any per-base view depend on it,
        # and a widening that quietly widened *everything* would be the same bug mirrored.
        self.assertIn("knowledge_base_id", str(db.statements[0].whereclause))
