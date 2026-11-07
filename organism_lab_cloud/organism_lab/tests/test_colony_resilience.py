"""Bounded information sharing and fault-containment simulation tests."""
import json
import tempfile
import unittest
from pathlib import Path

from organism_lab.colony_resilience import (
    explain_colony_resilience,
    run_colony_resilience_study,
    save_colony_resilience_study,
)


class ColonyResilienceTests(unittest.TestCase):
    def test_paired_run_is_reproducible_and_fault_is_contained_in_protected_arm(self):
        first = run_colony_resilience_study(seeds=12)
        second = run_colony_resilience_study(seeds=12)
        self.assertEqual(first, second)
        open_arm = first["arms"]["open_broadcast"]
        protected = first["arms"]["segmented_validated"]
        self.assertEqual(open_arm["mean_compromised_nodes"], 16)
        self.assertEqual(protected["mean_compromised_nodes"], 1)
        self.assertEqual(protected["mean_healthy_ready"], 15)
        self.assertGreater(protected["mean_rejected_bad_packets"], 0)
        self.assertEqual(len(open_arm["trials"]), 12)

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


if __name__ == "__main__":
    unittest.main()

