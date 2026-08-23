"""Measure whether the retrieval pipeline actually works, and whether a change helped.

Not a unit test. Unit tests answer "does this code do what it says"; this answers "does the
system give good answers", which is the only question that matters and the only one nothing
else in the repo asks.

Every threshold in the pipeline — the hop cap, the relevance floors, the modality split, the
candidate multiplier — is currently a defensible guess. This is what turns them into
measurements. Run it before a change and after, and keep the numbers.

    python scripts/eval.py --dataset datasets/golden.json
    python scripts/eval.py --dataset datasets/golden.json --baseline runs/before.json

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


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--tenant", required=True, help="Tenant UUID to run the questions as")
    parser.add_argument("--user", required=True, help="User UUID within that tenant")
    parser.add_argument("--out", type=Path, help="Write the summary here for later comparison")
    parser.add_argument("--baseline", type=Path, help="Compare against a previous summary")
    args = parser.parse_args()

    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    print(f"Running {len(cases)} cases...\n")

    results: list[CaseResult] = []
    for case in cases:
        result = await run_case(case, args.tenant, args.user)
        results.append(result)
        recall = "-" if result.recall is None else f"{result.recall:.2f}"
        status = result.error or f"{result.exit_reason} hops={result.hops} recall={recall}"
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

    from src.infrastructure.database.session import engine

    await engine.dispose()
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
