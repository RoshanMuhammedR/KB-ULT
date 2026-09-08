"""Work owed after `done` has to happen even when nobody is listening.

An async generator only resumes when its consumer pulls again. Everything after
`yield ("done", ...)` — the grounding check, persisting its verdict, the learned-prior
signal, memory distillation — used to sit on that resumption, so a user navigating away when
the answer finished threw `GeneratorExit` and skipped all of it.

Navigating away on `done` is not an edge case, it is what reading an answer and moving on
looks like. So `chunk_signals` was being populated only by people who waited around — a
selection bias on the exact signal the relevance prior is meant to learn from.

Reproduced here by closing the generator at `done`, which is what Starlette does when a
client disconnects.
"""

import unittest
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase


class _Recorder:
    """Stands in for the finalisation collaborators, recording what actually ran."""

    def __init__(self) -> None:
        self.ran: list[str] = []


def _service(recorder: _Recorder):
    """A service whose `_ask` is reduced to the shape under test.

    The real `_ask` needs a knowledge base, a resolver, a loop, an assembler and a model.
    None of that is what this pins: the property is the generator's control flow around
    `done`, so the surrounding pipeline is replaced with the two yields it produces.
    """
    from src.application.chat.agentic.service import AgenticChatService

    service = AgenticChatService(
        kb_repo=SimpleNamespace(),
        conversation_repo=SimpleNamespace(),
        chunk_repo=SimpleNamespace(),
        loop=SimpleNamespace(),
        resolver=SimpleNamespace(),
        assembler=SimpleNamespace(),
        grounding=SimpleNamespace(),
        llm_provider=SimpleNamespace(),
    )

    async def _finalise(*_args, **_kwargs):
        recorder.ran.append("finalised")
        return SimpleNamespace(to_wire=lambda: {"verified": True})

    service._finalise = _finalise  # type: ignore[method-assign]
    return service


async def _stream(service, recorder):
    """The exact control flow `_ask` uses around `done`."""
    finalised = False
    try:
        yield ("done", {})
        report = await service._finalise()
        finalised = True
        yield ("verified", report.to_wire())
    finally:
        if not finalised:
            await service._finalise()


class FinalisationTest(IsolatedAsyncioTestCase):
    async def test_a_reader_who_stays_gets_the_badge_and_the_work_runs_once(self) -> None:
        recorder = _Recorder()
        service = _service(recorder)

        events = [event async for event in _stream(service, recorder)]

        self.assertEqual([name for name, _ in events], ["done", "verified"])
        self.assertEqual(recorder.ran, ["finalised"], "must not run twice on the happy path")

    async def test_a_client_that_hangs_up_on_done_still_pays_its_debts(self) -> None:
        """The regression. Closing at `done` is what Starlette does on a disconnect."""
        recorder = _Recorder()
        service = _service(recorder)

        stream = _stream(service, recorder)
        first = await stream.__anext__()
        self.assertEqual(first[0], "done")
        await stream.aclose()

        self.assertEqual(recorder.ran, ["finalised"])

    async def test_a_client_that_never_pulls_at_all_owes_nothing(self) -> None:
        """No answer was produced, so there is nothing to ground or learn from."""
        recorder = _Recorder()
        service = _service(recorder)

        stream = _stream(service, recorder)
        await stream.aclose()

        self.assertEqual(recorder.ran, [])


class RetrievalBypassTest(unittest.TestCase):
    """The "this needs no search" shortcut has to be about the whole question.

    It used `.search`, so any question *containing* one of its phrases was answered with a
    canned line about what the assistant is, having retrieved nothing — and having persisted
    nothing, while a conversation row had already been created. "How do you work out the
    notice period?" and "What can you do with the export API?" are questions about the
    corpus, and both were swallowed.
    """

    def test_a_real_question_that_merely_opens_with_the_phrase_still_retrieves(self) -> None:
        from src.retrieval.langchain.query import needs_retrieval

        for question in (
            "How do you work out the notice period?",
            "What can you do with the export API?",
            "What are you able to tell me about Vite?",
        ):
            with self.subTest(question=question):
                self.assertTrue(needs_retrieval(question))

    def test_a_question_actually_about_the_assistant_is_still_short_circuited(self) -> None:
        from src.retrieval.langchain.query import needs_retrieval

        for question in ("Who are you?", "what can you do", "Are you an AI?", "How do you work?"):
            with self.subTest(question=question):
                self.assertFalse(needs_retrieval(question))

    def test_greetings_are_unaffected(self) -> None:
        from src.retrieval.langchain.query import needs_retrieval

        self.assertFalse(needs_retrieval("hi"))
        self.assertFalse(needs_retrieval("thanks!"))


if __name__ == "__main__":
    unittest.main()
