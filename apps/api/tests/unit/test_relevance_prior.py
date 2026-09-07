"""The prior must nudge, decay and forgive — never entrench.

A learned relevance prior has one catastrophic failure mode and it is invisible from the
inside: the passages it promotes get cited more, which strengthens them, which promotes them
further, until retrieval returns the workspace's greatest hits regardless of the question.
Every damping mechanism here exists to break that loop, and each is pinned separately, because
removing any one of them leaves a system that still looks like it works.

The other property pinned here is that the prior does not corrupt what it reorders.
`metadata[SCORE]` and `metadata["rerank_score"]` are read by the citation UI's relevance
percentage, the prompt's `score=` label, the dense threshold and the rerank floor — four
unrelated consumers, none of which should start reflecting a workspace's voting history.
"""

from datetime import datetime, timedelta, timezone
from unittest import TestCase

from langchain_core.documents import Document

from src.domain.entities import ChunkSignal
from src.retrieval.langchain.prior import PRIOR, PRIOR_RANK_DELTA, apply_prior, prior_value
from src.retrieval.langchain.retrievers import CHUNK_ID, SCORE

_NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)

_DAMPING = {
    "saturation": 10,
    "half_life_days": 30.0,
    "upvote_weight": 2.0,
    "downvote_weight": 3.0,
}


def _signal(chunk_id: str, *, days_ago: float = 0.0, **counters) -> ChunkSignal:
    from uuid import UUID

    return ChunkSignal(
        chunk_id=UUID(chunk_id),
        last_cited_at=_NOW - timedelta(days=days_ago),
        **counters,
    )


def _docs(n: int) -> list[Document]:
    """`n` documents in fused order, ids "0000...000N", descending cosine."""
    return [
        Document(
            page_content=f"passage {i}",
            metadata={CHUNK_ID: f"00000000-0000-0000-0000-00000000000{i}", SCORE: 1.0 - i / 100},
        )
        for i in range(n)
    ]


class DampingTests(TestCase):
    def test_citation_alone_earns_nothing(self) -> None:
        """The single most important property in this module.

        Being cited is exactly what the prior influences. If bare citation fed back into it,
        the loop would have no signal from outside itself and would amplify its own output
        forever. `cited` is recorded only as the denominator that makes the rest readable.
        """
        heavily_cited = _signal("00000000-0000-0000-0000-000000000001", cited=400)

        self.assertEqual(prior_value(heavily_cited, now=_NOW, **_DAMPING), 0.0)

    def test_evidence_saturates(self) -> None:
        """The 20th supported citation must be worth almost nothing.

        Without this a passage cited hundreds of times becomes an unremovable pin that no
        amount of contrary evidence can dislodge.
        """
        ten = prior_value(_signal("00000000-0000-0000-0000-000000000001", supported=10), now=_NOW, **_DAMPING)
        forty = prior_value(_signal("00000000-0000-0000-0000-000000000001", supported=40), now=_NOW, **_DAMPING)

        self.assertAlmostEqual(ten, 1.0, places=2)
        # Four times the evidence buys less than a third more standing, and the clamp holds.
        self.assertLessEqual(forty, 1.0)

    def test_a_passage_that_keeps_being_misread_goes_negative(self) -> None:
        """Without negative evidence the prior is a ratchet that only ever goes up."""
        bad = _signal("00000000-0000-0000-0000-000000000001", supported=1, unsupported=6)

        self.assertLess(prior_value(bad, now=_NOW, **_DAMPING), 0.0)

    def test_a_downvote_outweighs_an_upvote(self) -> None:
        """Being wrong costs more than being right pays — the asymmetry is the point."""
        up = prior_value(_signal("00000000-0000-0000-0000-000000000001", upvoted=1), now=_NOW, **_DAMPING)
        down = prior_value(_signal("00000000-0000-0000-0000-000000000001", downvoted=1), now=_NOW, **_DAMPING)

        self.assertGreater(up, 0.0)
        self.assertLess(down, 0.0)
        self.assertGreater(abs(down), abs(up))

    def test_a_human_verdict_outweighs_the_checkers(self) -> None:
        """It is the only signal here that is not a model grading its own work."""
        checker = _signal("00000000-0000-0000-0000-000000000001", supported=1)
        human = _signal("00000000-0000-0000-0000-000000000001", upvoted=1)

        self.assertGreater(
            prior_value(human, now=_NOW, **_DAMPING), prior_value(checker, now=_NOW, **_DAMPING)
        )

    def test_standing_halves_over_the_half_life(self) -> None:
        fresh = _signal("00000000-0000-0000-0000-000000000001", supported=10, days_ago=0)
        stale = _signal("00000000-0000-0000-0000-000000000001", supported=10, days_ago=30)

        self.assertAlmostEqual(
            prior_value(stale, now=_NOW, **_DAMPING),
            prior_value(fresh, now=_NOW, **_DAMPING) / 2,
            places=3,
        )

    def test_a_year_of_silence_leaves_almost_nothing(self) -> None:
        """Corpora go stale, and so should the belief that a passage answers something."""
        ancient = _signal("00000000-0000-0000-0000-000000000001", supported=10, days_ago=365)

        self.assertLess(prior_value(ancient, now=_NOW, **_DAMPING), 0.01)

    def test_a_naive_timestamp_does_not_raise(self) -> None:
        """A decayed prior is worth more than a 500 on the answer path."""
        signal = ChunkSignal(
            chunk_id=_signal("00000000-0000-0000-0000-000000000001").chunk_id,
            supported=5,
            last_cited_at=datetime(2026, 9, 1),  # naive
        )

        self.assertGreater(prior_value(signal, now=_NOW, **_DAMPING), 0.0)


class ApplyPriorTests(TestCase):
    def test_the_bonus_cannot_leapfrog_a_strong_hit(self) -> None:
        """The structural cap: a maximal prior nudges, it does not rewrite the ranking.

        The passage at rank 5 has every counter maxed out. It should climb — and it must not
        reach rank 0, or the prior has become the ranking.
        """
        documents = _docs(10)
        priors = {
            documents[5].metadata[CHUNK_ID]: _signal(
                documents[5].metadata[CHUNK_ID], supported=50, upvoted=50
            )
        }

        result = apply_prior(documents, priors, max_shift=3, now=_NOW, **_DAMPING)

        moved_to = [d.metadata[CHUNK_ID] for d in result].index(documents[5].metadata[CHUNK_ID])
        self.assertLess(moved_to, 5, "a maximal prior should improve the rank")
        self.assertGreater(moved_to, 0, "a maximal prior must not take rank 0")

    def test_scores_are_left_byte_identical(self) -> None:
        """Four unrelated consumers read these numbers; none may see voting history."""
        documents = _docs(5)
        before = [d.metadata[SCORE] for d in documents]
        priors = {
            documents[3].metadata[CHUNK_ID]: _signal(
                documents[3].metadata[CHUNK_ID], supported=20, upvoted=10
            )
        }

        result = apply_prior(documents, priors, max_shift=3, now=_NOW, **_DAMPING)

        self.assertEqual(sorted(d.metadata[SCORE] for d in result), sorted(before))
        for document in result:
            self.assertNotIn("rerank_score", document.metadata)

    def test_a_pool_with_no_signal_comes_back_untouched(self) -> None:
        documents = _docs(6)
        original = [d.metadata[CHUNK_ID] for d in documents]

        result = apply_prior(documents, {}, max_shift=3, now=_NOW, **_DAMPING)

        self.assertEqual([d.metadata[CHUNK_ID] for d in result], original)

    def test_documents_without_a_signal_keep_their_relative_order(self) -> None:
        """A stable sort, so the fused order survives wherever the prior is silent."""
        documents = _docs(8)
        priors = {
            documents[7].metadata[CHUNK_ID]: _signal(
                documents[7].metadata[CHUNK_ID], supported=5
            )
        }

        result = apply_prior(documents, priors, max_shift=3, now=_NOW, **_DAMPING)
        unsignalled = [
            d.metadata[CHUNK_ID] for d in result if d.metadata[CHUNK_ID] != documents[7].metadata[CHUNK_ID]
        ]

        self.assertEqual(unsignalled, [d.metadata[CHUNK_ID] for d in documents[:7]])

    def test_a_demoted_passage_records_a_negative_delta(self) -> None:
        """`prior_rank_delta` is how eval sees the prior working, or entrenching."""
        documents = _docs(4)
        priors = {
            documents[0].metadata[CHUNK_ID]: _signal(
                documents[0].metadata[CHUNK_ID], unsupported=20, downvoted=10
            )
        }

        result = apply_prior(documents, priors, max_shift=3, now=_NOW, **_DAMPING)
        demoted = next(d for d in result if d.metadata[CHUNK_ID] == documents[0].metadata[CHUNK_ID])

        self.assertLess(demoted.metadata[PRIOR], 0.0)
        self.assertLess(demoted.metadata[PRIOR_RANK_DELTA], 0)

    def test_no_document_moves_further_than_the_cap(self) -> None:
        """The bound stated as a property, over a pool where every document has history.

        The single-case test above could pass on arithmetic that happens to work for one
        input. This one gives all ten passages maximal and opposing priors — the worst case
        for a bound that is enforced by a clamp rather than by construction — and asserts no
        passage moved more than `max_shift` positions in either direction.
        """
        documents = _docs(10)
        priors = {}
        for i, document in enumerate(documents):
            chunk_id = document.metadata[CHUNK_ID]
            # Alternating: half pushed maximally up, half maximally down.
            priors[chunk_id] = (
                _signal(chunk_id, supported=50, upvoted=50)
                if i % 2
                else _signal(chunk_id, unsupported=50, downvoted=50)
            )

        result = apply_prior(documents, priors, max_shift=3, now=_NOW, **_DAMPING)

        for new_rank, document in enumerate(result):
            old_rank = documents.index(document)
            self.assertLessEqual(
                abs(new_rank - old_rank), 3, f"passage moved {abs(new_rank - old_rank)} places"
            )

    def test_an_empty_pool_is_not_an_error(self) -> None:
        self.assertEqual(apply_prior([], {}, max_shift=3, **_DAMPING), [])


if __name__ == "__main__":
    import unittest

    unittest.main()
