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

    @property
    def recall(self) -> float | None:
        """Did retrieval find the passages the answer needed?

        The single most diagnostic number here: generation cannot fix what retrieval never
        surfaced, so a low recall makes every downstream metric meaningless.
        """
        if not self.expected:
            return None
        found = len(set(self.expected) & set(self.retrieved))
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
    )

    try:
        async with session_scope() as db:
            service = build_agentic_chat_service(db, get_settings())
            answer_parts: list[str] = []
            async for event, payload in service.ask_stream(None, case["question"]):
                if event == "delta":
                    answer_parts.append(str(payload))
                elif event == "citations":
                    result.retrieved = [c["chunk_id"] for c in payload if c.get("chunk_id")]
                elif event == "done":
                    result.hops = payload.get("hops", 0)
                    result.exit_reason = payload.get("exit_reason", "")
                    result.fell_back = bool(payload.get("insufficient_context"))
                elif event == "verified":
                    # Retrieval recall says the right passage was found; this says the
                    # answer written from it actually follows from it. A pipeline can
                    # score perfectly on the first and still be inventing claims.
                    result.checked = payload.get("checked", 0)
                    result.supported = payload.get("supported", 0)
                    result.unsupported = len(payload.get("unsupported", [])) + len(
                        payload.get("invalid", [])
                    )
                    if result.checked:
                        result.verified = bool(payload.get("verified"))
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
    missed_fallbacks = [r for r in expected_fallbacks if not r.fell_back]

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
        "answered_when_it_should_not_have": len(missed_fallbacks),
        "fell_back_when_it_should_not_have": len(unexpected_fallbacks),
        # Answer quality, as distinct from retrieval quality. None when nothing was
        # checkable at all, which is a dataset problem rather than a score of zero.
        "grounded_rate": round(total_supported / total_checked, 4) if total_checked else None,
        "claims_checked": total_checked,
        "unsupported_citations": total_checked - total_supported,
        "by_kind": {
            kind: _kind_summary([r for r in results if r.kind == kind])
            for kind in KINDS
            if any(r.kind == kind for r in results)
        },
    }


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


def compare(current: dict, baseline: dict) -> list[str]:
    """Say plainly which way each number moved. A change that improves recall and doubles
    p95 latency is a trade-off to decide on, not a regression to block — so this reports
    rather than judges."""
    lines = []
    for metric, higher_is_better in (
        ("recall_at_k", True),
        ("mrr", True),
        ("grounded_rate", True),
        ("unsupported_citations", False),
        ("p50_latency_ms", False),
        ("p95_latency_ms", False),
        ("answered_when_it_should_not_have", False),
        ("fell_back_when_it_should_not_have", False),
    ):
        now, before = current.get(metric), baseline.get(metric)
        if now is None or before is None:
            continue
        delta = now - before
        if abs(delta) < 1e-9:
            marker = "="
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
        value = summary[metric]
        if value is None:
            failures.append(f"  {metric:38} not measured (floor {floor})")
        elif value < floor:
            failures.append(f"  {metric:38} {value} < {floor}")
    return failures


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--tenant", required=True, help="Tenant UUID to run the questions as")
    parser.add_argument("--user", required=True, help="User UUID within that tenant")
    parser.add_argument("--out", type=Path, help="Write the summary here for later comparison")
    parser.add_argument("--baseline", type=Path, help="Compare against a previous summary")
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
    print(f"Running {len(cases)} cases...\n")

    results: list[CaseResult] = []
    for case in cases:
        result = await run_case(case, args.tenant, args.user)
        results.append(result)
        recall = "-" if result.recall is None else f"{result.recall:.2f}"
        grounded = "-" if result.verified is None else f"{result.supported}/{result.checked}"
        status = result.error or (
            f"{result.exit_reason} hops={result.hops} recall={recall} grounded={grounded}"
        )
        print(f"  {result.id:32} {result.latency_ms:7.0f}ms  {status}")

    summary = summarise(results, cases)
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
