"""Validation and failure-isolation on the feedback routes.

Two things are under test and neither is the repository, which has its own tests.

**What the route refuses.** A verdict on a user's own question is meaningless and would
record a rating against no citations; a message id belonging to another conversation must not
be writable through this path. Both are checked before anything is written.

**What the route survives.** The reader's click is the durable thing. Counter updates are
derived data, and a failure there must never turn a successful vote into an error the user
sees — they would click again, and the click that already landed would be counted twice.
"""

import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.domain.entities import Conversation, Message, MessageRole
from src.http.routes import conversations as conversation_routes
from src.infrastructure.database.session import get_db

_CONVERSATION_ID = uuid4()
_ASSISTANT_ID = uuid4()
_USER_MESSAGE_ID = uuid4()
_CHUNK_ID = uuid4()


def _conversation() -> Conversation:
    return Conversation(
        id=_CONVERSATION_ID,
        knowledge_base_id=uuid4(),
        title="A thread",
        messages=[
            Message(
                id=_USER_MESSAGE_ID,
                conversation_id=_CONVERSATION_ID,
                role=MessageRole.USER,
                content="What is the notice period?",
            ),
            Message(
                id=_ASSISTANT_ID,
                conversation_id=_CONVERSATION_ID,
                role=MessageRole.ASSISTANT,
                content="Thirty days [1].",
                citations=[{"chunk_id": str(_CHUNK_ID)}],
            ),
        ],
    )


class _FakeConversationRepo:
    def __init__(self, db=None, conversation=None) -> None:
        self.conversation = conversation

    async def get_with_messages(self, conversation_id):
        if self.conversation is None or conversation_id != self.conversation.id:
            return None
        return self.conversation


class _FakeFeedbackRepo:
    calls: list = []
    previous: int | None = None

    def __init__(self, db=None) -> None:
        pass

    async def set(self, message_id, rating):
        _FakeFeedbackRepo.calls.append(("set", message_id, rating))
        return _FakeFeedbackRepo.previous

    async def clear(self, message_id):
        _FakeFeedbackRepo.calls.append(("clear", message_id))
        return _FakeFeedbackRepo.previous


class _FakeSignalRepo:
    calls: list = []
    fail = False

    def __init__(self, db=None) -> None:
        pass

    async def apply_feedback(self, chunk_ids, *, previous, current):
        if _FakeSignalRepo.fail:
            raise RuntimeError("connection reset")
        _FakeSignalRepo.calls.append((list(chunk_ids), previous, current))


class FeedbackRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeFeedbackRepo.calls = []
        _FakeFeedbackRepo.previous = None
        _FakeSignalRepo.calls = []
        _FakeSignalRepo.fail = False

        app = FastAPI()
        app.include_router(conversation_routes.router)
        app.dependency_overrides[get_db] = lambda: None
        self.client = TestClient(app)

        conversation = _conversation()
        self._patches = [
            patch.object(
                conversation_routes,
                "ConversationRepository",
                lambda db: _FakeConversationRepo(db, conversation),
            ),
            patch.object(conversation_routes, "MessageFeedbackRepository", _FakeFeedbackRepo),
            patch.object(conversation_routes, "ChunkSignalRepository", _FakeSignalRepo),
        ]
        for item in self._patches:
            item.start()

    def tearDown(self) -> None:
        for item in self._patches:
            item.stop()

    def _url(self, message_id=_ASSISTANT_ID, conversation_id=_CONVERSATION_ID) -> str:
        return f"/conversations/{conversation_id}/messages/{message_id}/feedback"

    def test_a_thumbs_up_is_recorded_against_the_answers_citations(self) -> None:
        response = self.client.put(self._url(), json={"rating": 1})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["rating"], 1)
        self.assertEqual(_FakeSignalRepo.calls, [([_CHUNK_ID], None, 1)])

    def test_changing_your_mind_passes_both_verdicts_through(self) -> None:
        """The counters move by the difference, so the route must report what it replaced."""
        _FakeFeedbackRepo.previous = 1

        self.client.put(self._url(), json={"rating": -1})

        self.assertEqual(_FakeSignalRepo.calls, [([_CHUNK_ID], 1, -1)])

    def test_retracting_reports_a_current_verdict_of_none(self) -> None:
        _FakeFeedbackRepo.previous = -1

        response = self.client.delete(self._url())

        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(_FakeSignalRepo.calls, [([_CHUNK_ID], -1, None)])

    def test_rating_a_user_message_is_rejected(self) -> None:
        """Rating your own question is meaningless and would record against no citations."""
        response = self.client.put(self._url(message_id=_USER_MESSAGE_ID), json={"rating": 1})

        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(_FakeFeedbackRepo.calls, [])

    def test_a_message_from_another_conversation_is_a_404(self) -> None:
        response = self.client.put(self._url(message_id=uuid4()), json={"rating": 1})

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(_FakeFeedbackRepo.calls, [])

    def test_an_unknown_conversation_is_a_404_not_a_403(self) -> None:
        """A conversation in another tenant is invisible, not forbidden.

        Answering 403 would confirm the id exists, which is exactly what a 404 refuses to
        reveal — and the tenant filter makes the two cases indistinguishable here anyway.
        """
        response = self.client.put(self._url(conversation_id=uuid4()), json={"rating": 1})

        self.assertEqual(response.status_code, 404, response.text)

    def test_an_out_of_range_rating_never_reaches_the_handler(self) -> None:
        """`Literal[-1, 1]` means validation rejects it, so the CHECK constraint is a backstop
        rather than the first line of defence."""
        for rating in (0, 5, -2, "up"):
            with self.subTest(rating=rating):
                response = self.client.put(self._url(), json={"rating": rating})
                self.assertEqual(response.status_code, 422)
        self.assertEqual(_FakeFeedbackRepo.calls, [])

    def test_a_failed_counter_write_still_returns_the_vote_as_saved(self) -> None:
        """The click is committed first and on its own.

        Failing the response here would show an error over a vote that actually landed, and
        the user would click again — double-counting the one thing in this system that comes
        from a human.
        """
        _FakeSignalRepo.fail = True

        response = self.client.put(self._url(), json={"rating": 1})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(_FakeFeedbackRepo.calls, [("set", _ASSISTANT_ID, 1)])


if __name__ == "__main__":
    unittest.main()
