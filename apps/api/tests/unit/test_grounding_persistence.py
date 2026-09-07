"""The verified badge has to survive a page reload.

The grounding check runs *after* the answer has streamed, deliberately — as a blocking step
it adds over a second to every response and forces the whole answer to be buffered, which
destroys time-to-first-token. The cost of that choice is that the verdict does not exist when
the message row is written, so it needs a second write.

What is pinned here: the checker records which passages an answer actually cited (3c
attributes outcomes back to them), the wire shape stays exactly what the client already
renders, and the second write tolerates a row that has since been deleted.
"""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from uuid import uuid4

from langchain_core.documents import Document

from src.application.chat.agentic.context import Citation
from src.application.chat.agentic.grounding import GroundingChecker, GroundingReport
from src.infrastructure.repositories.postgres_conversation_repository import (
    ConversationRepository,
)


class _Verdicts:
    """Stands in for `llm.with_structured_output(_Verdict)`.

    `supported` is keyed by a substring of the claim so a test can make one specific claim
    fail without depending on the order checks happen to run in.
    """

    def __init__(self, unsupported_marker: str | None = None) -> None:
        self.unsupported_marker = unsupported_marker
        self.claims: list[str] = []

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        claim = messages[1]["content"]
        self.claims.append(claim)
        supported = not (self.unsupported_marker and self.unsupported_marker in claim)
        return SimpleNamespace(supported=supported)


def _citations(count: int) -> list[Citation]:
    return [
        Citation(ordinal=i + 1, document=Document(page_content=f"passage {i + 1}", metadata={}))
        for i in range(count)
    ]


class CitedOrdinalsTest(IsolatedAsyncioTestCase):
    async def test_a_passage_cited_in_several_sentences_is_recorded_once(self) -> None:
        """`checked` counts claims; `cited_ordinals` counts passages.

        Conflating them would weight a passage by how chatty the answer happened to be about
        it, which is a property of the prose rather than of the retrieval.
        """
        checker = GroundingChecker(_Verdicts())
        answer = "The limit is ten [1]. It resets nightly [1]. Billing is monthly [2]."

        report = await checker.check(answer, _citations(2))

        self.assertEqual(report.checked, 3)
        self.assertEqual(report.cited_ordinals, [1, 2])

    async def test_an_invented_ordinal_is_never_recorded_as_cited(self) -> None:
        """A hallucinated citation number points at no passage, so it credits none.

        This is the failure that most needs to not feed a learned prior: the model naming a
        source it was never shown must not end up strengthening some unrelated passage.
        """
        checker = GroundingChecker(_Verdicts())

        report = await checker.check("Real [1]. Invented [7].", _citations(1))

        self.assertEqual(report.cited_ordinals, [1])
        self.assertEqual(report.invalid_ordinals, [7])
        self.assertFalse(report.verified)

    async def test_a_cited_passage_is_recorded_even_when_it_was_misread(self) -> None:
        """Cited and supported are separate facts, and 3c needs both.

        A passage that keeps getting cited for claims it does not support is exactly what
        negative evidence is for — so it has to appear in `cited_ordinals` to be counted
        against, not be quietly dropped.
        """
        checker = GroundingChecker(_Verdicts(unsupported_marker="wrong"))

        report = await checker.check("Right [1]. This is wrong [2].", _citations(2))

        self.assertEqual(report.cited_ordinals, [1, 2])
        self.assertEqual(report.unsupported_ordinals, [2])

    def test_cited_ordinals_stays_out_of_the_wire_shape(self) -> None:
        """It is a server-side signal, and this dict is written to a row on every answer."""
        report = GroundingReport(checked=1, supported=1, cited_ordinals=[1])

        self.assertEqual(
            set(report.to_wire()), {"verified", "checked", "supported", "unsupported", "invalid"}
        )


class _FakeSession:
    """Enough AsyncSession for `set_grounding`: one scalars() result, and a commit flag."""

    def __init__(self, model=None) -> None:
        self.model = model
        self.committed = False
        self.info: dict = {}

    async def scalars(self, _statement):
        return SimpleNamespace(first=lambda: self.model)

    async def commit(self) -> None:
        self.committed = True

    async def flush(self) -> None:  # pragma: no cover - only reached inside a unit_of_work
        pass

    def in_transaction(self) -> bool:
        return False


class SetGroundingTest(IsolatedAsyncioTestCase):
    async def test_the_verdict_lands_on_the_message(self) -> None:
        model = SimpleNamespace(grounding=None)
        session = _FakeSession(model)
        wire = GroundingReport(checked=2, supported=2).to_wire()

        await ConversationRepository(session).set_grounding(uuid4(), wire)

        self.assertIs(model.grounding["verified"], True)
        self.assertEqual(model.grounding["checked"], 2)
        self.assertTrue(session.committed)

    async def test_a_deleted_message_is_not_an_error(self) -> None:
        """The user can delete the conversation while its answer is still being verified.

        Losing the badge for a message that no longer exists is the correct outcome. Raising
        here would surface as a stream error on an answer that had already succeeded.
        """
        session = _FakeSession(model=None)

        await ConversationRepository(session).set_grounding(uuid4(), {"verified": True})

        self.assertFalse(session.committed)


if __name__ == "__main__":
    import unittest

    unittest.main()
