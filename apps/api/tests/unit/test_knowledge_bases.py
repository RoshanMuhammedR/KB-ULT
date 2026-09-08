"""Several knowledge bases, and the isolation that has to hold between them.

Before this, `get_default()` — "the oldest row in the tenant" — was the sole way every one of
fourteen call sites decided which base a request meant. With one base per tenant that was
invisible. With several it silently pins everything to the first: sources upload into it,
conversations belong to it, memories are recalled from it, and a newly created base is
unreachable through the whole API.

The sharpest edge is `_resolve_conversation`. It fetched a thread by id and never checked
which base it belonged to, so a thread started in B would have been answered from A's corpus
and A's memories. That is a cross-corpus leak inside one tenant, and nothing would have
reported it.
"""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from uuid import UUID, uuid4

from src.application.chat.agentic.service import AgenticChatService
from src.domain.entities import Conversation


class _KbRepo:
    """Only knows about the bases it was given — like the tenant-filtered repository."""

    def __init__(self, ids: list[UUID], default: UUID | None = None) -> None:
        self.ids = ids
        self.default_id = default or (ids[0] if ids else uuid4())

    async def get(self, knowledge_base_id):
        if knowledge_base_id in self.ids:
            return SimpleNamespace(id=knowledge_base_id)
        return None

    async def ensure_default(self):
        return SimpleNamespace(id=self.default_id)


class _ConversationRepo:
    def __init__(self, existing: Conversation | None = None, attached=None) -> None:
        self.existing = existing
        self.attached = list(attached or [])
        self.created: list[Conversation] = []

    async def create(self, conversation):
        self.created.append(conversation)
        return conversation

    async def get(self, conversation_id):
        return self.existing

    async def attached_bases(self, conversation_id):
        return list(self.attached)

    async def attach_bases(self, conversation_id, knowledge_base_ids):
        for knowledge_base_id in knowledge_base_ids:
            if knowledge_base_id not in self.attached:
                self.attached.append(knowledge_base_id)


def _service(kb_repo, conversation_repo) -> AgenticChatService:
    return AgenticChatService(
        kb_repo=kb_repo,
        conversation_repo=conversation_repo,
        chunk_repo=SimpleNamespace(),
        loop=SimpleNamespace(),
        resolver=SimpleNamespace(),
        assembler=SimpleNamespace(),
        grounding=SimpleNamespace(),
        llm_provider=SimpleNamespace(),
    )


class ResolveConversationTest(IsolatedAsyncioTestCase):
    async def test_a_new_thread_attaches_what_was_asked_for(self) -> None:
        first, second = uuid4(), uuid4()
        conversations = _ConversationRepo()
        service = _service(_KbRepo([first, second]), conversations)

        conversation, bases = await service._resolve_conversation(None, "q", [first, second])

        self.assertEqual(bases, [first, second])
        self.assertEqual(conversations.attached, [first, second])
        # The thread records where it was started, which is what the sidebar groups by.
        self.assertEqual(conversation.knowledge_base_id, first)

    async def test_a_new_thread_with_no_choice_gets_the_default(self) -> None:
        """First run, and any client that predates the switcher."""
        default = uuid4()
        service = _service(_KbRepo([default], default=default), _ConversationRepo())

        _conversation, bases = await service._resolve_conversation(None, "q", None)

        self.assertEqual(bases, [default])

    async def test_an_existing_thread_uses_what_it_is_attached_to(self) -> None:
        """Not the tenant's oldest base, which is what every call site used to get."""
        started_in, other = uuid4(), uuid4()
        existing = Conversation(id=uuid4(), knowledge_base_id=started_in, title="t")
        conversations = _ConversationRepo(existing, attached=[started_in])
        service = _service(_KbRepo([other, started_in], default=other), conversations)

        _conversation, bases = await service._resolve_conversation(existing.id, "q", None)

        self.assertEqual(bases, [started_in])

    async def test_attaching_a_base_mid_thread_adds_it(self) -> None:
        started_in, extra = uuid4(), uuid4()
        existing = Conversation(id=uuid4(), knowledge_base_id=started_in, title="t")
        conversations = _ConversationRepo(existing, attached=[started_in])
        service = _service(_KbRepo([started_in, extra]), conversations)

        _conversation, bases = await service._resolve_conversation(existing.id, "q", [extra])

        self.assertEqual(sorted(map(str, bases)), sorted(map(str, [started_in, extra])))

    async def test_a_thread_whose_bases_were_all_deleted_falls_back(self) -> None:
        """It is still readable, and its old answers still cite what they cited."""
        started_in = uuid4()
        existing = Conversation(id=uuid4(), knowledge_base_id=started_in, title="t")
        conversations = _ConversationRepo(existing, attached=[])
        service = _service(_KbRepo([started_in]), conversations)

        _conversation, bases = await service._resolve_conversation(existing.id, "q", None)

        self.assertEqual(bases, [started_in])


class CrossTenantTest(IsolatedAsyncioTestCase):
    async def test_a_base_this_tenant_cannot_see_is_not_found(self) -> None:
        """404, never 403. Saying forbidden would confirm the id exists."""
        mine = uuid4()
        service = _service(_KbRepo([mine]), _ConversationRepo())

        with self.assertRaises(ValueError):
            await service._resolve_conversation(None, "q", [uuid4()])

    async def test_an_invisible_base_is_dropped_from_a_mixed_request(self) -> None:
        """Asking for one of mine and one of someone else's answers from mine only — it must
        not fail the whole question, and must not silently include the other."""
        mine = uuid4()
        service = _service(_KbRepo([mine]), _ConversationRepo())

        _conversation, bases = await service._resolve_conversation(None, "q", [mine, uuid4()])

        self.assertEqual(bases, [mine])

    async def test_duplicate_ids_are_collapsed(self) -> None:
        mine = uuid4()
        service = _service(_KbRepo([mine]), _ConversationRepo())

        _conversation, bases = await service._resolve_conversation(None, "q", [mine, mine])

        self.assertEqual(bases, [mine])


class RetrievalScopeTest(IsolatedAsyncioTestCase):
    async def test_the_query_filters_on_every_attached_base(self) -> None:
        """`IN`, not `==`. This is the one hot-path change, so the SQL is asserted."""
        from sqlalchemy import select
        from sqlalchemy.dialects import postgresql

        from src.infrastructure.database.models import EmbeddingModel
        from src.infrastructure.repositories.postgres_chunk_repository import EmbeddingRepository

        ids = [uuid4(), uuid4()]
        distance = EmbeddingModel.vector.cosine_distance([0.1] * 3)
        statement = EmbeddingRepository._ready_chunks_base(ids, distance)

        sql = str(select(statement.subquery()).compile(dialect=postgresql.dialect()))

        self.assertIn("knowledge_base_id IN", sql)


if __name__ == "__main__":
    import unittest

    unittest.main()
