"""A delta smaller than the pipeline's disagreement with itself is not a result.

Four LLM components sit in the answer path — resolution, decomposition, reranking, grading —
and each is free to decide differently on identical input. Across three single runs of the
golden dataset `recall_at_k` read 0.88, 0.94 and 0.88, with real changes landing in between,
and nothing in the harness could say which of those moves were caused by the changes.

Every number recorded before this was n=1. A harness that cannot separate a result from its
noise cannot settle the question it exists to settle.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "ev", Path(__file__).resolve().parents[2] / "scripts" / "eval.py"
)
ev = importlib.util.module_from_spec(_spec)
sys.modules["ev"] = ev
_spec.loader.exec_module(ev)


def _run(recall, mrr=0.8):
    return {
        "recall_at_k": recall,
        "mrr": mrr,
        "cases": 33,
        "grounded_rate": None,
        "exit_reasons": {"sufficient": 10},
    }


class AggregateTest(unittest.TestCase):
    def test_a_numeric_metric_gains_its_spread(self) -> None:
        merged = ev.aggregate([_run(0.88), _run(0.94), _run(0.88)])

        self.assertEqual(merged["recall_at_k"]["mean"], 0.9)
        self.assertEqual(merged["recall_at_k"]["min"], 0.88)
        self.assertEqual(merged["recall_at_k"]["max"], 0.94)
        self.assertGreater(merged["recall_at_k"]["stdev"], 0.0)
        self.assertEqual(merged["runs"], 3)

    def test_structural_fields_are_left_alone(self) -> None:
        """Distributions and per-kind blocks are shapes, not measurements."""
        merged = ev.aggregate([_run(0.88), _run(0.94)])

        self.assertEqual(merged["exit_reasons"], {"sufficient": 10})

    def test_a_none_metric_is_not_averaged_into_a_number(self) -> None:
        """`grounded_rate` is None when nothing was checkable. Treating that as zero would
        invent a measurement out of its absence."""
        merged = ev.aggregate([_run(0.88), _run(0.94)])

        self.assertIsNone(merged["grounded_rate"])

    def test_a_single_run_passes_straight_through(self) -> None:
        """So every existing recorded run stays readable and comparable."""
        merged = ev.aggregate([_run(0.88)])

        self.assertEqual(merged["recall_at_k"], 0.88)

    def test_no_runs_is_not_a_crash(self) -> None:
        self.assertEqual(ev.aggregate([]), {})


class NoiseAwareCompareTest(unittest.TestCase):
    def test_a_move_inside_the_spread_is_called_noise(self) -> None:
        baseline = ev.aggregate([_run(0.88), _run(0.94), _run(0.88)])  # stdev ~0.028
        after = ev.aggregate([_run(0.91)])

        line = next(l for l in ev.compare(after, baseline) if "recall_at_k" in l)

        self.assertIn("noise", line)

    def test_a_move_beyond_the_spread_is_a_result(self) -> None:
        baseline = ev.aggregate([_run(0.88), _run(0.94), _run(0.88)])
        after = ev.aggregate([_run(0.99)])

        line = next(l for l in ev.compare(after, baseline) if "recall_at_k" in l)

        self.assertIn("better", line)
        self.assertNotIn("noise", line)

    def test_a_drop_beyond_the_spread_is_still_flagged(self) -> None:
        baseline = ev.aggregate([_run(0.88), _run(0.94), _run(0.88)])
        after = ev.aggregate([_run(0.60)])

        line = next(l for l in ev.compare(after, baseline) if "recall_at_k" in l)

        self.assertIn("WORSE", line)

    def test_without_a_repeated_baseline_nothing_is_suppressed(self) -> None:
        """An n=1 baseline has no known noise floor, so every move still reports. Silently
        treating unknown spread as zero is right: it under-claims rather than over-claims."""
        line = next(
            l for l in ev.compare(ev.aggregate([_run(0.91)]), ev.aggregate([_run(0.90)]))
            if "recall_at_k" in l
        )

        self.assertIn("better", line)


class ThresholdTest(unittest.TestCase):
    def test_a_gate_reads_the_mean_of_a_repeated_run(self) -> None:
        """The point of repeating: a run that scrapes over the bar by luck should not pass."""
        merged = ev.aggregate([_run(0.88), _run(0.94), _run(0.88)])

        self.assertEqual(ev.check_thresholds(merged, {"recall_at_k": 0.95}), [
            "  recall_at_k                            0.9 < 0.95"
        ])

    def test_a_mean_above_the_floor_passes(self) -> None:
        merged = ev.aggregate([_run(0.88), _run(0.94), _run(0.88)])

        self.assertEqual(ev.check_thresholds(merged, {"recall_at_k": 0.85}), [])


if __name__ == "__main__":
    unittest.main()
