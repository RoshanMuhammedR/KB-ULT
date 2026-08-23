"""Regression tests for the SSE answer stream.

Two properties are pinned here, both of which were once broken in production.

**The stream must drain cleanly.** `ask_in_conversation` used to bind the tenant contextvar
inside a *sync* generator and reset it in a `finally`. Starlette drove that generator through
`iterate_in_threadpool`, which runs every `next()` in a fresh `copy_context()`, so the token
was created in one Context and reset in another and `ContextVar.reset` raised - after the
whole answer had gone out on the wire. The browser reported a network error for an answer
that had actually succeeded and been committed. The generator is now an async generator
running in a single task and a single context, which makes that class of bug structurally
impossible rather than merely avoided; these tests hold the line anyway, because the cost of
regressing it is a silently broken response body.

**Nothing is persisted until the answer completes.** The question used to be appended and
committed before generation, so every failure left an orphan turn that `recent_messages` fed
into the next prompt - each retry made the prompt worse.

Neither is observable at the response level: the status is 200 and the body is complete.
What catches them is draining the generator the way Starlette does.
"""

import asyncio
import contextlib
import json
from contextvars import copy_context
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from src.application.chat.service import ChatService
from src.core.config import get_settings
from src.core.identity import Identity
from src.core.tenant_context import (
    current_tenant_id,
    current_user_id,
    reset_tenant_context,
    set_tenant_context,
    try_current_tenant_id,
)
from src.domain.entities import (
    AssetStatus,
    Chunk,
    Conversation,
    KnowledgeAsset,
    Message,
    MessageRole,
    RetrievalResult,
)
from src.http.routes.conversations import ask_in_conversation
from src.http.schemas.conversations import AskRequest


def _async_value(value):
    """A coroutine seam that always resolves to `value`, whatever it is called with."""

    async def _call(*args, **kwargs):
        return value

    return _call


def _async_stream(pieces):
    """An async-generator stand-in for `ILLMProvider.stream`."""

    def _call(messages):
        async def _gen():
            for piece in pieces:
                yield piece

        return _gen()

    return _call


async def _collect(agen) -> list:
    return [item async for item in agen]


TENANT = UUID("11111111-1111-1111-1111-111111111111")
USER = UUID("22222222-2222-2222-2222-222222222222")


class _StubChatService:
    """Yields the same event shapes as the real `ask_stream`, with no I/O."""

    def __init__(self, on_each_frame=None) -> None:
        self.on_each_frame = on_each_frame

    async def ask_stream(self, conversation_id, question):
        conversation = {"id": str(uuid4()), "title": "Stub"}
        for event, payload in (
            ("conversation", conversation),
            ("delta", "Hello"),
            ("delta", " there."),
            ("citations", []),
            ("done", {"user_message_id": str(uuid4()), "message_id": str(uuid4())}),
        ):
            if self.on_each_frame is not None:
                self.on_each_frame()
            yield (event, payload)


@contextlib.asynccontextmanager
async def _fake_session_scope():
    yield object()


async def _drain(response) -> list[str]:
    """Consume the response body exactly as Starlette's ASGI send loop does."""
    return [
        chunk.decode() if isinstance(chunk, bytes) else chunk
        async for chunk in response.body_iterator
    ]


async def _stream(chat_service) -> list[str]:
    """Call the route and drain it, with the stubs held in place for both.

    The patches must stay active across the drain, not just the call: a generator body does
    not execute until it is iterated, so patching only around `ask_in_conversation` would
    let the real service and a real database session escape into the test.
    """
    identity = Identity(tenant_id=TENANT, user_id=USER)
    with patch("src.http.routes.conversations.session_scope", _fake_session_scope), patch(
        "src.http.routes.conversations.build_agentic_chat_service", lambda db, settings: chat_service
    ):
        response = await ask_in_conversation(
            conversation_id="new",
            request=AskRequest(question="hi"),
            identity=identity,
            settings=get_settings(),
        )
        return await _drain(response)


class AnswerStreamDrainsCleanlyTest(IsolatedAsyncioTestCase):
    async def test_generator_completes_without_raising(self) -> None:
        # Before the fix this raised ValueError("... was created in a different Context")
        # on the final next(), after every frame had already been yielded.
        chunks = await _stream(_StubChatService())

        body = "".join(chunks)
        self.assertIn("event: done", body)
        self.assertIn("event: delta", body)

    async def test_every_frame_is_a_well_formed_sse_event(self) -> None:
        chunks = await _stream(_StubChatService())

        for chunk in chunks:
            self.assertTrue(chunk.startswith("event: "), chunk)
            self.assertTrue(chunk.endswith("\n\n"), chunk)
            data = chunk.split("data: ", 1)[1]
            json.loads(data)  # raises if the payload is not valid JSON

    async def test_tenant_context_resolves_on_every_frame(self) -> None:
        # The generator no longer binds the tenant itself — it relies on TenantContextMiddleware
        # having bound it in the enclosing context, which anyio's copy_context() carries into
        # each frame. Simulate that outer binding and assert every frame can still read it.
        seen: list[tuple] = []
        service = _StubChatService(
            on_each_frame=lambda: seen.append((current_tenant_id(), current_user_id()))
        )

        token = set_tenant_context(TENANT, USER)
        try:
            await _stream(service)
        finally:
            reset_tenant_context(token)

        self.assertEqual(len(seen), 5)
        self.assertTrue(all(pair == (TENANT, USER) for pair in seen), seen)


class _FakeConversationRepo:
    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def get(self, conversation_id):
        return Conversation(id=conversation_id, knowledge_base_id=uuid4(), title="Existing")

    async def create(self, conversation):
        return conversation

    async def recent_messages(self, conversation_id, limit):
        return list(self.messages)[-limit:]

    async def append_message(self, message):
        self.messages.append(message)
        return message


class _FakeKbRepo:
    async def ensure_default(self):
        return SimpleNamespace(id=uuid4())


def _chat_service(repo, llm_stream, results) -> ChatService:
    return ChatService(
        kb_repo=_FakeKbRepo(),
        embedding_provider=SimpleNamespace(embed_query=_async_value([0.0])),
        retriever=SimpleNamespace(retrieve=_async_value(results)),
        llm_provider=SimpleNamespace(stream=llm_stream),
        prompt_builder=SimpleNamespace(
            build=lambda *a, **k: [{"role": "user", "content": "hi"}],
            insufficient_context_answer=lambda: "I don't have enough context.",
        ),
        top_k=5,
        threshold=0.0,
        min_context_chunks=1,
        conversation_repo=repo,
    )


class NothingIsSavedUntilTheAnswerCompletesTest(IsolatedAsyncioTestCase):
    """The error copy promises "nothing was saved" — that has to be literally true.

    It used to be false: the question was appended (and committed) before retrieval, so every
    failure left an orphan turn that `recent_messages` fed into the *next* prompt, making each
    retry worse than the last.
    """

    def _result(self) -> RetrievalResult:
        return RetrievalResult(
            chunk=Chunk(text="context", chunk_index=0, metadata={}),
            asset=KnowledgeAsset(
                knowledge_base_id=uuid4(),
                filename="doc.pdf",
                source_type="pdf",
                storage_key="k",
                status=AssetStatus.READY,
            ),
            score=0.9,
        )

    async def test_a_failure_mid_answer_persists_nothing(self) -> None:
        repo = _FakeConversationRepo()

        async def exploding_stream(messages):
            yield "partial"
            raise RuntimeError("provider fell over")

        service = _chat_service(repo, exploding_stream, [self._result()])

        with self.assertRaises(RuntimeError):
            await _collect(service.ask_stream(uuid4(), "what about margins?"))

        self.assertEqual(repo.messages, [])

    async def test_a_successful_answer_persists_the_question_then_the_answer(self) -> None:
        repo = _FakeConversationRepo()
        service = _chat_service(repo, _async_stream(["all ", "good"]), [self._result()])

        await _collect(service.ask_stream(uuid4(), "what about margins?"))

        self.assertEqual([m.role for m in repo.messages], [MessageRole.USER, MessageRole.ASSISTANT])
        self.assertEqual(repo.messages[0].content, "what about margins?")
        self.assertEqual(repo.messages[1].content, "all good")

    async def test_the_insufficient_context_path_also_persists_the_pair(self) -> None:
        repo = _FakeConversationRepo()
        service = _chat_service(repo, _async_stream([]), [])  # no results at all

        await _collect(service.ask_stream(uuid4(), "what about margins?"))

        self.assertEqual([m.role for m in repo.messages], [MessageRole.USER, MessageRole.ASSISTANT])
        self.assertTrue(repo.messages[1].insufficient_context)

    async def test_a_retry_after_failure_does_not_inherit_an_orphan_question(self) -> None:
        # The amplifier: two failed attempts followed by a good one must leave a clean
        # two-message thread, not four unanswered questions plus an answer.
        repo = _FakeConversationRepo()

        async def exploding_stream(messages):
            raise RuntimeError("provider fell over")
            yield  # pragma: no cover - generator marker

        for _ in range(2):
            with self.assertRaises(RuntimeError):
                await _collect(
                    _chat_service(repo, exploding_stream, [self._result()]).ask_stream(
                        uuid4(), "what about margins?"
                    )
                )

        good = _chat_service(repo, _async_stream(["recovered"]), [self._result()])
        await _collect(good.ask_stream(uuid4(), "what about margins?"))

        self.assertEqual([m.role for m in repo.messages], [MessageRole.USER, MessageRole.ASSISTANT])


class ResetTenantContextAcrossContextsTest(TestCase):
    """`reset_tenant_context` must never be the thing that kills a response body."""

    def test_reset_with_a_foreign_token_does_not_raise(self) -> None:
        token = copy_context().run(set_tenant_context, TENANT, USER)

        reset_tenant_context(token)  # would raise ValueError before the fix

    def test_reset_with_a_foreign_token_fails_closed(self) -> None:
        # Falling back to "unset" is only safe because reads then raise rather than
        # silently resolving to the wrong tenant.
        token = copy_context().run(set_tenant_context, TENANT, USER)

        reset_tenant_context(token)

        self.assertIsNone(try_current_tenant_id())

    def test_normal_same_context_reset_still_restores_the_previous_value(self) -> None:
        outer = set_tenant_context(TENANT, USER)
        inner_tenant = uuid4()
        inner = set_tenant_context(inner_tenant, USER)

        self.assertEqual(current_tenant_id(), inner_tenant)
        reset_tenant_context(inner)
        self.assertEqual(current_tenant_id(), TENANT)

        reset_tenant_context(outer)
