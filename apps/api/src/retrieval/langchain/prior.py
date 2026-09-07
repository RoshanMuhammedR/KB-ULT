"""A bounded, decaying nudge to fusion order, learned from what passages actually did.

Retrieval has no memory without this. A passage that has answered the same question
correctly forty times starts from zero on the forty-first, and one that keeps being cited for
claims it does not support never sinks. The prior is the smallest mechanism that fixes both.

**It reorders ranks. It does not touch scores.** `metadata[SCORE]` and
`metadata["rerank_score"]` are read by four unrelated things — the citation UI's relevance
percentage (`Citation.to_wire`), the `score=` label in the prompt (`ContextAssembler._render`),
the dense retrieval threshold, and the per-modality rerank floor. Multiplying a learned weight
into either would break all four at once and, worse, would make the number the user sees a
function of the workspace's voting history rather than of the passage's fit to the question.
So the prior operates in the same rank space RRF already uses, and the scores come out of here
byte-identical to how they went in.

**It is not a retrieval arm.** An arm returning "the tenant's most-cited chunks" would surface
passages with no reference to the question at all, which is entrenchment in its purest form. A
prior is only defined over chunks some other arm already found.

**Five things stop it becoming a ratchet**, and removing any one of them is how this feature
turns into a system that recommends whatever it recommended yesterday:

1. `cited` never feeds it. Being retrieved is exactly what the prior influences, so a loop
   from citation back to rank has no external signal in it at all — it would amplify its own
   output forever. Only `supported`/`unsupported` (the grounding checker) and
   `upvoted`/`downvoted` (a human) count.
2. Logarithmic growth, so the 20th supported citation moves almost nothing and no passage
   becomes an unremovable pin.
3. Negative evidence, weighted higher than positive. Without it the prior can only ever go up.
4. Exponential time decay from `last_cited_at`, computed here at read time rather than by a
   job that rewrites rows.
5. A structural cap of `max_shift` positions. No passage moves further than that, in either
   direction, whatever its history. It breaks ties and nudges neighbours; it cannot rewrite
   the ranking.

**On that cap: it is expressed in ranks, not in RRF value, and the difference is not
cosmetic.** The obvious formulation — add `weight * prior * (1 / (rrf_k + 1))` to each
document's positional value — reads like a bound and is not one. At the default `rrf_k` of 60
the RRF curve is nearly flat: rank 0 is worth 0.01639 and rank 5 is worth 0.01515, a gap of
0.0012, while a maximal bonus at `weight = 0.3` is 0.0049 — four times the distance it was
supposed to be unable to cross. A passage could take rank 0 from anywhere in the pool on
history alone. Subtracting positions directly makes the bound exact and arithmetic-free.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import log1p

from langchain_core.documents import Document

from src.domain.entities import ChunkSignal
from src.retrieval.langchain.retrievers import CHUNK_ID

#: What the prior writes, for the trace and for eval. Never read by ranking itself.
PRIOR = "prior"
PRIOR_RANK_DELTA = "prior_rank_delta"


def prior_value(
    signal: ChunkSignal,
    *,
    saturation: int,
    half_life_days: float,
    upvote_weight: float,
    downvote_weight: float,
    now: datetime | None = None,
) -> float:
    """A passage's standing in [-1, 1]. Pure, so the damping is testable without a database.

    `saturation` sets where the logarithm flattens: at `saturation` supported citations the
    positive term is 1.0, and everything past that is a rounding error. It is a soft cap on
    how much history can matter, not a hard one.
    """
    positive = log1p(signal.supported + upvote_weight * signal.upvoted) / log1p(saturation)
    negative = log1p(signal.unsupported + downvote_weight * signal.downvoted) / log1p(saturation)
    standing = max(-1.0, min(1.0, positive - negative))

    if signal.last_cited_at is None:
        # Never cited: only votes contributed, and there is no date to decay from. Left
        # undecayed rather than zeroed — someone took the trouble to vote.
        return standing

    reference = now or datetime.now(timezone.utc)
    last = signal.last_cited_at
    if last.tzinfo is None:
        # Postgres returns tz-aware for `timestamptz`, but a naive value from a fixture or an
        # older row must not raise here — a decayed prior is worth more than a 500.
        last = last.replace(tzinfo=timezone.utc)

    days = max(0.0, (reference - last).total_seconds() / 86_400)
    return standing * (0.5 ** (days / half_life_days))


def apply_prior(
    documents: list[Document],
    priors: dict[str, ChunkSignal],
    *,
    max_shift: int,
    saturation: int,
    half_life_days: float,
    upvote_weight: float,
    downvote_weight: float,
    now: datetime | None = None,
) -> list[Document]:
    """Reorder a fused list by moving each document at most `max_shift` positions.

    A document's effective rank is `rank - max_shift * prior`: a maximal positive prior
    lifts it by exactly `max_shift` places, a maximal negative one drops it by the same, and
    everything in between moves proportionally. The bound is arithmetic rather than a clamp
    applied afterwards, so it holds for every input including ones nobody thought to test.

    Documents with no signal keep their position and their relative order — the sort is
    stable on the incoming rank, so a list the prior has nothing to say about comes back
    exactly as it arrived.
    """
    if not documents or not priors:
        return documents

    scored: list[tuple[float, int, Document]] = []

    for rank, document in enumerate(documents):
        signal = priors.get(document.metadata.get(CHUNK_ID) or "")
        value = 0.0
        if signal is not None:
            value = prior_value(
                signal,
                saturation=saturation,
                half_life_days=half_life_days,
                upvote_weight=upvote_weight,
                downvote_weight=downvote_weight,
                now=now,
            )
            document.metadata[PRIOR] = round(value, 4)
        # `rank` as the tiebreak keeps the sort stable, so fusion order decides every case
        # the prior does not.
        scored.append((rank - max_shift * value, rank, document))

    scored.sort(key=lambda item: (item[0], item[1]))

    reordered = []
    for new_rank, (_total, old_rank, document) in enumerate(scored):
        # Positive means the prior moved it up. Recorded for the trace and for eval's
        # entrenchment check; nothing in ranking reads it back.
        document.metadata[PRIOR_RANK_DELTA] = old_rank - new_rank
        reordered.append(document)
    return reordered
