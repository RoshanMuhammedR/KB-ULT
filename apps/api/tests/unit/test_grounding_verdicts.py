"""A verdict, a refutation and "could not check" are three different things.

`GroundingReport.verified` was `not unsupported and not invalid`, so an answer that cited
nothing had both lists empty and reported `verified: True` — stored on the message row and
sent on the wire as a positive verdict on an answer nobody had checked. The badge happened not
to render it, thanks to a separate `checked == 0` guard in the component, so this was a lie in
the data rather than on screen. It still reached 120 stored rows, and any future reader of
`messages.grounding` would have believed it.

The same shape appeared twice more: an unreachable judge returned `True` (so an outage
verified every answer in the run), and uncited sentences were not merely unverified but
uncounted — which is the entire hallucination surface of this system.
"""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from uuid import uuid4

from langchain_core.documents import Document

from src.application.chat.agentic.context import Citation
from src.application.chat.agentic.grounding import (
    GroundingChecker,
    GroundingReport,
    count_uncited_sentences,
)


class _Judge:
    """Stands in for `llm.with_structured_output(_Verdict)`."""

    def __init__(self, *, supported=True, fail=False) -> None:
        self.supported = supported
        self.fail = fail
        self.calls = 0

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.fail:
            raise RuntimeError("gateway unreachable")
        return SimpleNamespace(supported=self.supported)


def _citations(count: int) -> list[Citation]:
    return [
        Citation(ordinal=i + 1, document=Document(page_content=f"passage {i + 1}", metadata={}))
        for i in range(count)
    ]


class VerdictStatesTest(TestCase):
    def test_nothing_checked_is_not_a_verdict(self) -> None:
        self.assertIsNone(GroundingReport().verified)

    def test_an_outage_is_not_a_verdict(self) -> None:
        """Every claim unreachable must read as "not verified", never as verified."""
        self.assertIsNone(GroundingReport(unchecked=4).verified)

    def test_checked_and_sound_is_true(self) -> None:
        self.assertIs(GroundingReport(checked=2, supported=2).verified, True)

    def test_checked_and_unsound_is_false(self) -> None:
        report = GroundingReport(checked=2, supported=1, unsupported_ordinals=[2])

        self.assertIs(report.verified, False)

    def test_an_invented_citation_is_a_verdict_even_with_nothing_checked(self) -> None:
        """A number pointing at no passage is the most alarming outcome here.

        It has `checked == 0`, so treating "nothing checked" as "no verdict" without this
        clause would make the worst case indistinguishable from a plain refusal.
        """
        self.assertIs(GroundingReport(invalid_ordinals=[7]).verified, False)


class UncitedSentencesTest(TestCase):
    def test_an_uncited_assertion_is_counted(self) -> None:
        answer = (
            "The limit is ten requests per minute [1]. "
            "It cannot be raised by support staff under any circumstances."
        )

        self.assertEqual(count_uncited_sentences(answer), 1)

    def test_a_fully_cited_answer_counts_none(self) -> None:
        self.assertEqual(
            count_uncited_sentences("The limit is ten requests per minute, always [1]."), 0
        )

    def test_list_scaffolding_is_not_an_assertion(self) -> None:
        self.assertEqual(count_uncited_sentences("## Summary\n- yes\n- no\nSources:"), 0)

    def test_bullets_split_so_one_list_is_not_one_claim(self) -> None:
        """Splitting on terminal punctuation alone made a whole bullet list a single
        "sentence", which the judge then rejected for being incoherent rather than untrue."""
        answer = (
            "- The first bullet asserts something substantial and long enough to count\n"
            "- The second bullet asserts something else that is also substantial enough"
        )

        self.assertEqual(count_uncited_sentences(answer), 2)


class GroupedCitationsTest(IsolatedAsyncioTestCase):
    async def test_a_grouped_citation_is_checked(self) -> None:
        """`[1, 2]` matched nothing before, so the claim went unchecked *and* neither passage
        recorded a signal — the learned prior never saw an answer that cited two sources."""
        judge = _Judge()

        report = await GroundingChecker(judge).check(
            "Both halves are documented together [1, 2].", _citations(2)
        )

        self.assertEqual(report.checked, 2)
        self.assertEqual(report.cited_ordinals, [1, 2])

    async def test_a_range_citation_expands(self) -> None:
        judge = _Judge()

        report = await GroundingChecker(judge).check(
            "This spans several passages [1-3].", _citations(3)
        )

        self.assertEqual(sorted(report.cited_ordinals), [1, 2, 3])


class UnreachableJudgeTest(IsolatedAsyncioTestCase):
    async def test_an_outage_verifies_nothing(self) -> None:
        """The circumstance where the badge is worth least must not be where it looks
        strongest. Returning True on an exception counted the claim as checked and supported.
        """
        judge = _Judge(fail=True)

        report = await GroundingChecker(judge).check("A claim [1].", _citations(1))

        self.assertEqual(report.checked, 0)
        self.assertEqual(report.supported, 0)
        self.assertEqual(report.unchecked, 1)
        self.assertIsNone(report.verified)

    async def test_an_outage_is_not_recorded_as_unsupported_either(self) -> None:
        """`_record_signals` writes unsupported verdicts into `chunk_signals`. Counting an
        outage as a refutation would train the learned prior on gateway weather."""
        judge = _Judge(fail=True)

        report = await GroundingChecker(judge).check("A claim [1].", _citations(1))

        self.assertEqual(report.unsupported_ordinals, [])


class WireShapeTest(TestCase):
    def test_the_wire_carries_the_three_states_and_the_counts(self) -> None:
        wire = GroundingReport(checked=1, supported=1, uncited_sentences=2, unchecked=1).to_wire()

        self.assertEqual(
            set(wire),
            {
                "verified",
                "checked",
                "supported",
                "unsupported",
                "invalid",
                "uncited_sentences",
                "unchecked",
            },
        )
        self.assertNotIn("cited_ordinals", wire)


if __name__ == "__main__":
    import unittest

    unittest.main()
