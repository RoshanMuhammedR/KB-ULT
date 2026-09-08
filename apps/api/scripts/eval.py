"""Measure whether the retrieval pipeline actually works, and whether a change helped.

Not a unit test. Unit tests answer "does this code do what it says"; this answers "does the
system give good answers", which is the only question that matters and the only one nothing
else in the repo asks.

Every threshold in the pipeline — the hop cap, the relevance floors, the modality split, the
candidate multiplier — is currently a defensible guess. This is what turns them into
measurements. Run it before a change and after, and keep the numbers.

    python scripts/eval.py --dataset scripts/datasets/golden.json --tenant <uuid> --user <uuid>
    python scripts/eval.py ... --out runs/after.json --baseline runs/before.json
    python scripts/eval.py ... --fail-under recall_at_k=0.7,grounded_rate=0.9
    python scripts/eval.py ... --repeat 3 --out runs/baseline.json    # with its own spread

**Use `--repeat` for anything you intend to compare against.** Four LLM components sit in the
answer path - resolution, decomposition, reranking, grading - and each may decide differently
on identical input. Three single runs of this dataset read 0.88, 0.94 and 0.88 for
`recall_at_k` with changes landing in between, and there was no way to tell which of those
moves were caused by the changes. A run recorded with `--repeat` carries its standard
deviation, and `--baseline` then marks any smaller delta as `noise` instead of letting it be
read as a result.

Two flags exist specifically to judge the learned relevance prior, which cannot be evaluated
by running the same questions repeatedly — doing that measures how well it memorised them:

    RETRIEVAL_PRIOR_ENABLED=1 python scripts/eval.py ... --warm 3      # shape across passes
    RETRIEVAL_PRIOR_ENABLED=1 python scripts/eval.py ... --holdout     # does it generalise

Ship the prior only if holdout recall is flat-or-up and `citation_concentration` has not
risen. Concentration climbing while recall holds is the signature of entrenchment, and it is
invisible to every other number here.

The dataset is a JSON list. `expected_chunks` may be omitted for cases where the point is
the *behaviour* rather than a specific passage — an out-of-corpus question that must trigger
the fallback, or an injection attempt that must be summarised rather than obeyed:

    [
      {
        "id": "notice-period",
        "question": "What is the notice period?",
        "kind": "single_hop",
        "expected_chunks": ["<chunk-uuid>"],
        "reference_answer": "Thirty days, per the termination clause.",
        "expect_fallback": false
      }
    ]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.event_loop import configure_event_loop  # noqa: E402

configure_event_loop()

from src.core.tenant_context import reset_tenant_context, set_tenant_context  # noqa: E402
from src.infrastructure.database.session import session_scope  # noqa: E402

# The kinds a good dataset covers. Named here because a set that is all `single_hop` will
# report excellent numbers and tell you nothing about the cases that actually break.
KINDS = (
    "single_hop",       # one passage answers it
    "multi_hop",        # needs two retrievals
    "exact_identifier", # error codes, config keys - the lexical arm's reason to exist
    "out_of_corpus",    # must fall back, must not invent
    "follow_up",        # only answerable after query resolution
    "injection",        # a poisoned document that must be reported, never obeyed
)


@dataclass
class CaseResult:
    id: str
    kind: str
    latency_ms: float
    hops: int
    exit_reason: str
    retrieved: list[str] = field(default_factory=list)
    expected: list[str] = field(default_factory=list)
    #: "all" (every expected chunk required) or "any" (they are alternatives). See `recall`.
    match: str = "all"
    answer: str = ""
    fell_back: bool = False
    error: str = ""
    # From the `verified` frame, which arrives after `done`. `verified` stays None when the
    # answer cited nothing to check — a fallback, or an answer with no citation markers —
    # which is different from "checked and found unsupported" and must not be averaged in.
    verified: bool | None = None
    checked: int = 0
    supported: int = 0
    unsupported: int = 0
    #: Sentences that asserted something and cited nothing. Not a verdict — an uncited
    #: sentence may be true — but it is the shape a confident invention takes, so it is
    #: reported rather than folded into a rate.
    uncited_sentences: int = 0
    #: Claims the grounding judge could not be reached for.
    unchecked: int = 0

    @property
    def recall(self) -> float | None:
        """Did retrieval find the passages the answer needed?

        The single most diagnostic number here: generation cannot fix what retrieval never
        surfaced, so a low recall makes every downstream metric meaningless.

        `match` says what the listed chunks mean, and getting it wrong silently misreports
        the system rather than failing:

        * `all` (default) — every listed chunk is required. Correct for a multi-hop question,
          where the answer genuinely needs both halves.
        * `any` — the listed chunks are alternatives, and finding one is a hit. Correct
          wherever several passages answer the question equally well, which small-to-big
          chunking makes common: "Vite" appears in nine chunks of this corpus, and a
          question about the build tool is answered correctly by at least three of them.

        Without `any`, the only honest option is to pin a single chunk and score every other
        correct passage as a total miss — which is how a working retriever gets a recall of
        0.00 on a question it answered perfectly. Listing the alternatives under `all` is no
        better: finding one of three would score 0.33 for a complete answer.
        """
        if not self.expected:
            return None
        found = len(set(self.expected) & set(self.retrieved))
        if self.match == "any":
            return 1.0 if found else 0.0
        return found / len(self.expected)

    @property
    def reciprocal_rank(self) -> float | None:
        """1/rank of the first expected passage. Rewards putting it near the top, not just
        somewhere in the list — the model reads the top of the context most carefully."""
        if not self.expected:
            return None
        for position, chunk_id in enumerate(self.retrieved, start=1):
            if chunk_id in self.expected:
                return 1.0 / position
        return 0.0


async def run_case(case: dict[str, Any], tenant_id: str, user_id: str) -> CaseResult:
    from uuid import UUID

    from src.composition import build_agentic_chat_service
    from src.core.config import get_settings

    tokens = set_tenant_context(UUID(tenant_id), UUID(user_id))
    started = time.perf_counter()
    result = CaseResult(
        id=case["id"],
        kind=case.get("kind", "single_hop"),
        latency_ms=0.0,
        hops=0,
        exit_reason="",
        expected=case.get("expected_chunks", []),
        match=case.get("match", "all"),
    )

    try:
        async with session_scope() as db:
            service = build_agentic_chat_service(db, get_settings())
            answer_parts: list[str] = []
            async for event, payload in service.ask_stream(None, case["question"]):
                if event == "delta":
                    answer_parts.append(str(payload))
                elif event == "citations":
                    # `matched_chunk_ids`, not just `chunk_id`. Several children of one
                    # section collapse into a single citation, so reading only the labelled
                    # id made the siblings invisible — a multi-hop case whose two expected
                    # chunks shared a section was capped at 0.5 recall however well retrieval
                    # had actually done. Falls back for answers written before the field.
                    result.retrieved = [
                        chunk_id
                        for citation in payload
                        for chunk_id in (citation.get("matched_chunk_ids") or [citation.get("chunk_id")])
                        if chunk_id
                    ]
                elif event == "done":
                    result.hops = payload.get("hops", 0)
                    result.exit_reason = payload.get("exit_reason", "")
                    result.fell_back = bool(payload.get("insufficient_context"))
                    # `ask_stream` catches every internal failure and yields a normal-looking
                    # `done`, so the `except` below is unreachable for anything that happens
                    # inside the pipeline. Without reading this the harness reported zero
                    # errors through a total crash, and `--fail-under` could not gate on it.
                    if payload.get("error"):
                        result.error = f"pipeline: {payload['error']}"
                elif event == "verified":
                    # Retrieval recall says the right passage was found; this says the
                    # answer written from it actually follows from it. A pipeline can
                    # score perfectly on the first and still be inventing claims.
                    result.checked = payload.get("checked", 0)
                    result.supported = payload.get("supported", 0)
                    result.unsupported = len(payload.get("unsupported", [])) + len(
                        payload.get("invalid", [])
                    )
                    result.uncited_sentences = payload.get("uncited_sentences", 0)
                    result.unchecked = payload.get("unchecked", 0)
                    # `verified` is now tri-state on the wire: None means nothing was
                    # checkable. Read it straight rather than re-deriving it from `checked`
                    # — the old `if result.checked:` guard is exactly why the harness could
                    # not see that the server was reporting `verified: True` for answers it
                    # had never checked. A harness that repairs the value it is measuring
                    # cannot measure it.
                    result.verified = payload.get("verified")
            result.answer = "".join(answer_parts)
    except Exception as exc:  # noqa: BLE001 - one bad case must not end the run
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        reset_tenant_context(tokens)
        result.latency_ms = (time.perf_counter() - started) * 1000

    return result


def summarise(results: list[CaseResult], cases: list[dict]) -> dict[str, Any]:
    by_id = {case["id"]: case for case in cases}
    recalls = [r.recall for r in results if r.recall is not None]
    rrs = [r.reciprocal_rank for r in results if r.reciprocal_rank is not None]
    latencies = sorted(r.latency_ms for r in results)

    # A fallback is correct when it was expected and wrong when it was not. Counting them
    # together as "fallback rate" hides both failures.
    expected_fallbacks = [r for r in results if by_id[r.id].get("expect_fallback")]
    unexpected_fallbacks = [
        r for r in results if r.fell_back and not by_id[r.id].get("expect_fallback")
    ]
    # Not every non-fallback is an invention, and conflating the two overstates the failure
    # this product cares most about.
    #
    # `insufficient_context` is set only by the deterministic fallback path, which runs when
    # retrieval found nothing at all. An out-of-corpus question whose topic is *adjacent* to
    # real content still retrieves passages, so the loop exits `max_hops`, an answer is
    # generated, and the model itself says "the retrieved context does not cover this". That
    # is the correct outcome reached by a different route, and scoring it as an invention
    # hides the fact that the pipeline is behaving.
    #
    # The two are told apart by whether the answer made any *cited* claim. Citing nothing
    # means asserting nothing about the corpus, which is what a refusal is. This is a
    # property of the answer rather than a phrase-match on its wording, so it does not rot
    # the first time the model rewords a refusal.
    #
    # It is not airtight: an answer that asserts something from the model's own knowledge
    # without citing would also count zero claims, and that is the most dangerous failure
    # here. `uncited_answers` is reported separately so it stays visible rather than being
    # averaged away — a number worth reading by hand when it moves.
    answered_anyway = [r for r in expected_fallbacks if not r.fell_back and r.checked > 0]
    refused_in_prose = [r for r in expected_fallbacks if not r.fell_back and r.checked == 0]

    # Pooled across the run rather than averaged per case: a case with eight claims is
    # eight chances to be wrong, and averaging per-case rates would let one heavily-cited
    # bad answer hide behind several lightly-cited good ones.
    total_checked = sum(r.checked for r in results)
    total_supported = sum(r.supported for r in results)

    return {
        "cases": len(results),
        "errors": sum(1 for r in results if r.error),
        "recall_at_k": round(statistics.fmean(recalls), 4) if recalls else None,
        "mrr": round(statistics.fmean(rrs), 4) if rrs else None,
        "p50_latency_ms": round(_percentile(latencies, 0.50)),
        "p95_latency_ms": round(_percentile(latencies, 0.95)),
        "mean_hops": round(statistics.fmean([r.hops for r in results]), 2) if results else 0,
        "hop_distribution": _distribution([r.hops for r in results]),
        "exit_reasons": _distribution([r.exit_reason or "error" for r in results]),
        # Answering out-of-corpus questions anyway is the failure this product exists to
        # avoid, so it is reported on its own rather than folded into an accuracy number.
        # An out-of-corpus question answered with cited claims: the failure this product
        # exists to avoid, and the only one of these three that is unambiguously bad.
        "answered_when_it_should_not_have": len(answered_anyway),
        # Refused, but by generating prose rather than by falling back — so it cost a full
        # retrieval loop and an answering call to say "I don't know". Correct, and wasteful.
        "refused_without_falling_back": len(refused_in_prose),
        "fell_back_when_it_should_not_have": len(unexpected_fallbacks),
        # Answer quality, as distinct from retrieval quality. None when nothing was
        # checkable at all, which is a dataset problem rather than a score of zero.
        "grounded_rate": round(total_supported / total_checked, 4) if total_checked else None,
        "claims_checked": total_checked,
        "unsupported_citations": total_checked - total_supported,
        # The entrenchment tell. A learned prior that is genuinely helping leaves this flat;
        # one that is collapsing onto a workspace's greatest hits pushes it up while recall
        # holds steady, which is exactly the case no other metric here would catch.
        "citation_concentration": _citation_concentration(results),
        # Answers the server reported a positive verdict on without checking anything. Must
        # be 0. It is a self-check on the harness as much as on the pipeline: the metric
        # exists because the previous version of this file silently corrected the value it
        # was supposed to be measuring.
        "verified_without_checking": sum(
            1 for r in results if r.verified is True and r.checked == 0
        ),
        # Sentences across the run that asserted something and cited nothing. Read it, do not
        # gate on it: some uncited sentences are honest refusals. A jump is worth looking at.
        "uncited_sentences": sum(r.uncited_sentences for r in results),
        # Claims lost to an unreachable judge. A non-zero value means grounded_rate is
        # measured over less than the whole run and should be read with that in mind.
        "unchecked_claims": sum(r.unchecked for r in results),
        # Answers that made no cited claim at all. A refusal looks like this and so does an
        # answer written from the model's own knowledge, so this is a number to read rather
        # than gate on: a rise means either more honest refusals or more uncited assertion,
        # and only reading a few tells you which.
        "uncited_answers": sum(1 for r in results if not r.fell_back and r.checked == 0),
        "by_kind": {
            kind: _kind_summary([r for r in results if r.kind == kind])
            for kind in KINDS
            if any(r.kind == kind for r in results)
        },
    }


def _citation_concentration(results: list[CaseResult]) -> float | None:
    """Share of all retrievals that went to the busiest 5% of passages.

    A corpus answering a varied question set should spread its citations around. If a small
    set of passages starts appearing everywhere, retrieval has stopped responding to the
    question — which is what a prior gone wrong looks like from the outside, and it can
    happen while recall on already-seen questions stays perfect.

    Computed over retrieved chunks rather than cited ones so it measures what the prior
    actually reorders, and so it is defined even for a run where nothing was cited.
    """
    counts: dict[str, int] = {}
    for result in results:
        for chunk_id in result.retrieved:
            counts[chunk_id] = counts.get(chunk_id, 0) + 1
    if not counts:
        return None

    total = sum(counts.values())
    top_n = max(1, round(len(counts) * 0.05))
    busiest = sorted(counts.values(), reverse=True)[:top_n]
    return round(sum(busiest) / total, 4)


def _kind_summary(results: list[CaseResult]) -> dict[str, Any]:
    recalls = [r.recall for r in results if r.recall is not None]
    return {
        "cases": len(results),
        "recall": round(statistics.fmean(recalls), 4) if recalls else None,
        "p95_latency_ms": round(_percentile(sorted(r.latency_ms for r in results), 0.95)),
    }


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, int(round(fraction * (len(values) - 1))))
    return values[index]


def _distribution(values: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def aggregate(summaries: list[dict]) -> dict:
    """Fold repeated runs of the same dataset into one summary carrying its own spread.

    **The harness needs this to be worth trusting.** Four LLM components sit in the answer
    path — resolution, decomposition, reranking, grading — and each is free to decide
    differently on identical input. Across three single runs of this dataset `recall_at_k`
    read 0.88, 0.94 and 0.88 with changes landing in between, and there was no way to tell
    which of those moves were caused by the changes and which were the pipeline disagreeing
    with itself. A harness that cannot separate a result from its noise cannot settle the
    question it exists to settle.

    Numeric metrics become `{mean, min, max, stdev, runs}`. Everything else — distributions,
    per-kind blocks, case counts — is taken from the first run, since those are structural
    rather than measured.

    `stdev` is the population standard deviation over the runs, which is what `compare` reads
    to decide whether a delta is bigger than the pipeline's own disagreement with itself.
    """
    if not summaries:
        return {}
    if len(summaries) == 1:
        return summaries[0]

    merged = dict(summaries[0])
    merged["runs"] = len(summaries)

    for metric in summaries[0]:
        values = [s.get(metric) for s in summaries]
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in values):
            continue
        merged[metric] = {
            "mean": round(statistics.fmean(values), 4),
            "min": min(values),
            "max": max(values),
            # Population, not sample: these are all the runs there were, not a sample of some
            # larger set of runs.
            "stdev": round(statistics.pstdev(values), 4),
            "runs": len(values),
        }
    return merged


def _value(metric_value):
    """The number to compare, whether the run recorded a bare value or an aggregate."""
    if isinstance(metric_value, dict):
        return metric_value.get("mean")
    return metric_value


def _noise(metric_value) -> float:
    """How much this metric moved between identical runs. Zero when unknown."""
    if isinstance(metric_value, dict):
        return metric_value.get("stdev") or 0.0
    return 0.0


def compare(current: dict, baseline: dict) -> list[str]:
    """Say plainly which way each number moved. A change that improves recall and doubles
    p95 latency is a trade-off to decide on, not a regression to block — so this reports
    rather than judges."""
    lines = []
    for metric, higher_is_better in (
        ("recall_at_k", True),
        ("mrr", True),
        ("grounded_rate", True),
        ("citation_concentration", False),
        ("verified_without_checking", False),
        ("uncited_sentences", False),
        ("refused_without_falling_back", False),
        ("unsupported_citations", False),
        ("p50_latency_ms", False),
        ("p95_latency_ms", False),
        ("answered_when_it_should_not_have", False),
        ("fell_back_when_it_should_not_have", False),
    ):
        now = _value(current.get(metric))
        before = _value(baseline.get(metric))
        if now is None or before is None:
            continue

        delta = now - before
        # The noise floor: how much this metric moves between identical runs. A change
        # smaller than the pipeline's own disagreement with itself is not a result, however
        # much one would like it to be. Both sides contribute, so a baseline taken with
        # `--repeat` protects every later comparison against it.
        floor = max(_noise(current.get(metric)), _noise(baseline.get(metric)))

        if abs(delta) < 1e-9:
            marker = "="
        elif abs(delta) <= floor:
            marker = f"noise (+/-{floor:g})"
        elif (delta > 0) == higher_is_better:
            marker = "better"
        else:
            marker = "WORSE"
        lines.append(f"  {metric:38} {before:>9} -> {now:>9}   {marker}")
    return lines


def parse_thresholds(raw: str) -> dict[str, float]:
    """`recall_at_k=0.7,grounded_rate=0.9` -> a dict. Raises on anything malformed.

    Deliberately strict: a typo'd metric name that silently gated on nothing would make a
    green CI run mean less than no gate at all.
    """
    thresholds: dict[str, float] = {}
    for clause in raw.split(","):
        clause = clause.strip()
        if not clause:
            continue
        name, _, value = clause.partition("=")
        if not _:
            raise ValueError(f"--fail-under expects metric=value, got {clause!r}")
        thresholds[name.strip()] = float(value)
    return thresholds


def check_thresholds(summary: dict[str, Any], thresholds: dict[str, float]) -> list[str]:
    """Metrics that came in under their floor, as printable lines.

    A metric that is absent or None fails rather than passes. `grounded_rate` is None when
    nothing was checkable, and treating "we measured nothing" as "we met the bar" is how a
    gate quietly stops gating.
    """
    failures = []
    for metric, floor in thresholds.items():
        if metric not in summary:
            failures.append(f"  {metric:38} not reported by this run")
            continue
        # `_value` unwraps an aggregate from `--repeat`. Gating on the mean is the point of
        # repeating: a run that scrapes over the bar by luck should not pass, and one that
        # dips under it by luck should not fail.
        value = _value(summary[metric])
        if value is None:
            failures.append(f"  {metric:38} not measured (floor {floor})")
        elif value < floor:
            failures.append(f"  {metric:38} {value} < {floor}")
    return failures


def split_holdout(cases: list[dict]) -> tuple[list[dict], list[dict]]:
    """Halve the dataset into a set that builds signal and a set that is scored on it.

    **This is the measurement that tells the two outcomes apart.** A prior that genuinely
    helps and a prior that is entrenching look identical on questions it has already seen —
    both push recall up, because both are learning to return what was returned before. The
    difference only shows on questions the signal was not built from: real generalisation
    lifts those too, while entrenchment leaves them flat or drags them down as retrieval
    collapses toward a handful of well-worn passages.

    Split on a stable hash of the case id rather than on position or `random`, so the same
    dataset produces the same halves on every run — otherwise a comparison against a saved
    baseline is comparing two different experiments. Interleaving by index would also
    correlate the split with dataset order, which tends to group cases by kind.
    """
    warm, holdout = [], []
    for case in cases:
        digest = hashlib.sha256(str(case["id"]).encode("utf-8")).digest()
        (warm if digest[0] % 2 else holdout).append(case)
    return warm, holdout


async def run_all(
    cases: list[dict], tenant_id: str, user_id: str, *, quiet: bool = False
) -> list[CaseResult]:
    """Run every case, printing a line each unless asked not to."""
    results: list[CaseResult] = []
    for case in cases:
        result = await run_case(case, tenant_id, user_id)
        results.append(result)
        if quiet:
            continue
        recall = "-" if result.recall is None else f"{result.recall:.2f}"
        grounded = "-" if result.verified is None else f"{result.supported}/{result.checked}"
        status = result.error or (
            f"{result.exit_reason} hops={result.hops} recall={recall} grounded={grounded}"
        )
        print(f"  {result.id:32} {result.latency_ms:7.0f}ms  {status}")
    return results


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--tenant", required=True, help="Tenant UUID to run the questions as")
    parser.add_argument("--user", required=True, help="User UUID within that tenant")
    parser.add_argument("--out", type=Path, help="Write the summary here for later comparison")
    parser.add_argument("--baseline", type=Path, help="Compare against a previous summary")
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help="Run the whole dataset N times and report each metric's mean and spread. Four "
        "LLM components sit in the answer path, so identical input does not give identical "
        "output; without this, no delta smaller than the pipeline's own disagreement with "
        "itself can honestly be attributed to a change.",
    )
    parser.add_argument(
        "--warm",
        type=int,
        default=0,
        metavar="N",
        help="Run the dataset N times first to build up signal, reporting each pass. A "
        "prior that helps is flat-or-up across passes; one that entrenches rises on pass 2 "
        "and then falls.",
    )
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="Split the dataset in half: build signal on one half, score on the other. The "
        "only way to tell a prior that generalises from one that has memorised the "
        "questions its signal came from.",
    )
    parser.add_argument(
        "--fail-under",
        metavar="METRIC=VALUE,...",
        help="Exit non-zero if a metric is below its floor, e.g. "
        "recall_at_k=0.7,grounded_rate=0.9. This is what makes the harness a CI gate "
        "rather than a report nobody reads.",
    )
    args = parser.parse_args()

    thresholds = parse_thresholds(args.fail_under) if args.fail_under else {}

    cases = json.loads(args.dataset.read_text(encoding="utf-8"))

    scored_cases = cases
    if args.holdout:
        warm_cases, scored_cases = split_holdout(cases)
        print(f"Holdout: building signal on {len(warm_cases)}, scoring {len(scored_cases)}\n")
        # The warm half's own numbers are never reported. Its only job is to leave signal in
        # `chunk_signals`; scoring it would be scoring the questions the prior just learned.
        await run_all(warm_cases, args.tenant, args.user, quiet=True)

    for pass_number in range(args.warm):
        print(f"Warming pass {pass_number + 1}/{args.warm}...")
        warmed = await run_all(scored_cases, args.tenant, args.user, quiet=True)
        pass_summary = summarise(warmed, scored_cases)
        # Printed per pass because the *shape* across passes is the signal: rising and then
        # falling is entrenchment, flat-or-up is a prior doing its job.
        print(
            f"  recall={pass_summary['recall_at_k']} mrr={pass_summary['mrr']} "
            f"concentration={pass_summary['citation_concentration']}\n"
        )

    summaries = []
    for attempt in range(max(1, args.repeat)):
        label = (
            f"Run {attempt + 1}/{args.repeat} of {len(scored_cases)} cases..."
            if args.repeat > 1
            else f"Running {len(scored_cases)} cases..."
        )
        print(label + "\n")
        # Only the first run prints per-case lines; the rest would bury the summary.
        results = await run_all(scored_cases, args.tenant, args.user, quiet=attempt > 0)
        summaries.append(summarise(results, scored_cases))
        if args.repeat > 1:
            latest = summaries[-1]
            print(
                f"  recall={latest['recall_at_k']} mrr={latest['mrr']} "
                f"grounded={latest['grounded_rate']} p50={latest['p50_latency_ms']}\n"
            )

    summary = aggregate(summaries)
    print("\n" + json.dumps(summary, indent=2))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nWrote {args.out}")

    if args.baseline and args.baseline.exists():
        print("\nAgainst baseline:")
        for line in compare(summary, json.loads(args.baseline.read_text(encoding="utf-8"))):
            print(line)

    failures = check_thresholds(summary, thresholds)
    if failures:
        print("\nBelow threshold:")
        for line in failures:
            print(line)

    from src.infrastructure.database.session import engine

    await engine.dispose()
    return 1 if summary["errors"] or failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
