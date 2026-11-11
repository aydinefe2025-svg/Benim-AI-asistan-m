"""Bounded information sharing and fault-containment simulation tests."""
import json
import tempfile
import unittest
from pathlib import Path

from organism_lab.colony_resilience import (
    explain_colony_resilience,
    run_colony_resilience_study,
    save_colony_resilience_study,
    validate_colony_resilience_report,
    paired_trial_rows,
    _report_digest,
)


class ColonyResilienceTests(unittest.TestCase):
    def test_paired_run_is_reproducible_and_fault_is_contained_in_protected_arm(self):
        first = run_colony_resilience_study(seeds=12)
        second = run_colony_resilience_study(seeds=12)
        self.assertEqual(first, second)
        open_arm = first["arms"]["open_broadcast"]
        protected = first["arms"]["segmented_validated"]
        self.assertGreater(open_arm["mean_compromised_nodes"], 1)
        self.assertLess(open_arm["mean_compromised_nodes"], 16)
        self.assertEqual(protected["mean_compromised_nodes"], 1)
        self.assertGreater(protected["mean_healthy_ready"], 0)
        self.assertGreater(protected["mean_rejected_bad_packets"], 0)
        self.assertEqual(len(open_arm["trials"]), 12)
        self.assertGreater(len({row["compromised_nodes"] for row in open_arm["trials"]}), 1)
        self.assertEqual({row["compromised_nodes"] for row in protected["trials"]}, {1})

    def test_paired_trial_rows_expose_per_seed_differences(self):
        report = run_colony_resilience_study(seeds=5)
        rows = paired_trial_rows(report)
        self.assertEqual(len(rows), 5)
        self.assertEqual([row["Tohum"] for row in rows], list(range(5)))
        self.assertTrue(all(row["Etkilenmiş ajan farkı"] < 0 for row in rows))
        self.assertGreater(len({row["Etkilenmiş ajan farkı"] for row in rows}), 1)

    def test_paired_trial_rows_reject_fault_mismatch(self):
        report = run_colony_resilience_study(seeds=3)
        report["arms"]["segmented_validated"]["trials"][0]["faulted_node"] += 1
        report["sha256"] = _report_digest(report)
        with self.assertRaisesRegex(ValueError, "seed or fault"):
            paired_trial_rows(report)

    def test_plain_language_explanation_states_simulation_limit(self):
        text = explain_colony_resilience(run_colony_resilience_study(seeds=3))
        self.assertIn("Ne denendi?", text)
        self.assertIn("sanal", text)
        self.assertIn("güvenlik garantisi", text)

    def test_versioned_save_and_readback(self):
        report = run_colony_resilience_study(seeds=3)
        with tempfile.TemporaryDirectory() as tmp:
            latest = Path(tmp) / "colony-resilience-latest.json"
            saved = save_colony_resilience_study(report, latest)
            restored = json.loads(latest.read_text(encoding="utf-8"))
            self.assertEqual(restored, saved)
            self.assertTrue((Path(tmp) / "colony-resilience-runs" /
                             f"colony-resilience-{saved['run_id']}.json").exists())

    def test_rejects_unbounded_or_invalid_inputs(self):
        for args in (
            {"seeds": True},
            {"seeds": 51},
            {"population": 33},
            {"population": 15, "compartments": 4},
            {"fault_tick": 9},
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                run_colony_resilience_study(**args)

    def test_explanation_rejects_unknown_report(self):
        with self.assertRaises(ValueError):
            explain_colony_resilience({"schema": "fake"})

    def test_tampering_is_detected_before_display_or_save(self):
        report = run_colony_resilience_study(seeds=3)
        report["arms"]["open_broadcast"]["mean_compromised_nodes"] = 0
        with self.assertRaisesRegex(ValueError, "integrity"):
            validate_colony_resilience_report(report)
        with self.assertRaisesRegex(ValueError, "integrity"):
            explain_colony_resilience(report)


if __name__ == "__main__":
    unittest.main()
