"""Reciprocal Rank Fusion — combine several rankings of the same items into one.

Retrieval runs two arms over the same chunks: dense (cosine similarity over embeddings) and
lexical (`ts_rank_cd` over a tsvector). Their scores live on completely incomparable scales,
so any attempt to add or average them needs a normalisation step that is arbitrary and
fragile.

RRF sidesteps that entirely by throwing the scores away and keeping only the *ranks*:

    score(item) = Σ_arms  weight_arm / (k + rank_in_arm)

Two properties earn it its place here:

  * An item found by **both** arms outranks one found brilliantly by only one — which is
    exactly the judgement you want when a chunk is both semantically close and contains the
    literal search term.
  * The `k` constant damps the head of each list, so an arm that is confidently wrong about
    its top hit cannot drag that hit to the top of the fused result.

`k = 60` is the value from Cormack, Clarke & Büttcher (SIGIR 2009), chosen empirically there
across several benchmarks. Nothing about this codebase makes a different value obviously
better, so the paper's default stands.

Pure functions over plain lists: no database, no I/O, no framework.
"""

from __future__ import annotations

from typing import Hashable, Sequence, TypeVar

T = TypeVar("T", bound=Hashable)

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[T]],
    *,
    k: int = DEFAULT_RRF_K,
    weights: Sequence[float] | None = None,
) -> list[T]:
    """Fuse several ranked lists into one, best first.

    `rankings` is one ordered sequence per arm, each already sorted best-first and containing
    whatever identifies an item (here: chunk ids). An item may appear in any, all, or only one
    of them. `weights` defaults to equal influence per arm.

    Ties are broken by best rank achieved in any single arm, then by first appearance, so the
    output is deterministic — two identical inputs always fuse to the same order, which
    matters when debugging why a passage was or wasn't retrieved.
    """
    if weights is None:
        weights = [1.0] * len(rankings)
    if len(weights) != len(rankings):
        raise ValueError("weights must have one entry per ranking")

    scores: dict[T, float] = {}
    best_rank: dict[T, int] = {}
    first_seen: dict[T, int] = {}
    order = 0

    for ranking, weight in zip(rankings, weights, strict=True):
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
            if item not in best_rank or rank < best_rank[item]:
                best_rank[item] = rank
            if item not in first_seen:
                first_seen[item] = order
                order += 1

    return sorted(
        scores,
        key=lambda item: (-scores[item], best_rank[item], first_seen[item]),
    )
