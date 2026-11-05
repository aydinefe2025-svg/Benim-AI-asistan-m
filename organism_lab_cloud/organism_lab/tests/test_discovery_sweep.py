import json
import tempfile
import unittest
from pathlib import Path

from organism_lab.discovery_sweep import (list_versioned_discovery_sweeps,
                                          run_discovery_sweep, save_discovery_sweep,
                                          validate_discovery_sweep)


class DiscoverySweepTests(unittest.TestCase):
    def test_screen_and_confirmation_are_reproducible_and_use_disjoint_seeds(self):
        options = {"screening_seeds": (1, 2, 3), "confirmation_seeds": (101, 102, 103),
                   "mutation_rates": (0.0, 0.1), "steps": 20, "shift_tick": 8, "capacity": 16}
        first = run_discovery_sweep(**options)
        second = run_discovery_sweep(**options)
        self.assertEqual(first, second)
        self.assertFalse(set(first["design"]["screening_seeds"]) &
                         set(first["design"]["confirmation_seeds"]))
        self.assertIn(first["status"], {"no_positive_screening_candidate",
                                        "replicated_simulation_candidate",
                                        "not_reproduced_on_confirmation_seeds"})
        self.assertIn("toy simulation", " ".join(first["interpretation"]["limits"]))
        self.assertLessEqual(len(first["robustness"]), 3)
        self.assertEqual(first["interpretation"]["robustness"]["tested_shift_count"],
                         len(first["robustness"]))
        for condition in first["robustness"]:
            self.assertIn(condition["shift_tick"], {5, 10, 15})
            self.assertEqual(condition["paired_seeds"], 3)
        self.assertTrue(validate_discovery_sweep(first))
        tampered = {**first, "screening": []}
        with self.assertRaises(ValueError):
            validate_discovery_sweep(tampered)

    def test_persistence_is_atomic_and_marks_simulation_only_status(self):
        report = run_discovery_sweep(screening_seeds=(0, 1, 2),
                                     confirmation_seeds=(10, 11, 12),
                                     mutation_rates=(0.0, 0.1), steps=12,
                                     shift_tick=5, capacity=8)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "discovery.json"
            saved = save_discovery_sweep(report, target)
            restored = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(restored, saved)
            self.assertTrue(restored["generated_at"])
            self.assertTrue(restored["run_id"])
            self.assertFalse(target.with_suffix(".json.tmp").exists())
            self.assertTrue(validate_discovery_sweep(restored))

            archived_path = target.parent / "discovery-sweeps" / f"discovery-sweep-{saved['run_id']}.json"
            self.assertEqual(json.loads(archived_path.read_text(encoding="utf-8")), saved)

            second = save_discovery_sweep(report, target)
            self.assertNotEqual(second["run_id"], saved["run_id"])
            self.assertEqual(json.loads(archived_path.read_text(encoding="utf-8")), saved)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), second)
            self.assertEqual(len(list((target.parent / "discovery-sweeps").glob("*.json"))), 2)

    def test_rejects_overlapping_or_unbounded_inputs(self):
        base = {"screening_seeds": (1, 2, 3), "confirmation_seeds": (4, 5, 6),
                "mutation_rates": (0.0, 0.1), "steps": 20, "shift_tick": 8}
        for change in ({"confirmation_seeds": (3, 4, 5)}, {"steps": 501},
                       {"mutation_rates": (0.1, 0.2)}):
            args = {**base, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                run_discovery_sweep(**args)


    def test_first_versioned_save_preserves_legacy_latest_report_exactly(self):
        report = run_discovery_sweep(screening_seeds=(0, 1, 2),
                                     confirmation_seeds=(10, 11, 12),
                                     mutation_rates=(0.0, 0.1), steps=12,
                                     shift_tick=5, capacity=8)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "discovery-sweep-latest.json"
            legacy_document = {**report, "generated_at": "2026-11-01T00:00:00+00:00"}
            previous = json.dumps(legacy_document, separators=(",", ":")).encode("utf-8")
            target.write_bytes(previous)

            saved = save_discovery_sweep(report, target)
            preserved = list((target.parent / "discovery-sweeps").glob("discovery-sweep-preserved-*.json"))
            self.assertEqual(len(preserved), 1)
            self.assertEqual(preserved[0].read_bytes(), previous)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), saved)
            listed = list_versioned_discovery_sweeps(target.parent / "discovery-sweeps")
            self.assertEqual(listed[-1][1], legacy_document)


    def test_history_lists_only_valid_versioned_reports_newest_first(self):
        report = run_discovery_sweep(screening_seeds=(0, 1, 2),
                                     confirmation_seeds=(10, 11, 12),
                                     mutation_rates=(0.0, 0.1), steps=12,
                                     shift_tick=5, capacity=8)
        with tempfile.TemporaryDirectory() as temporary:
            latest = Path(temporary) / "latest.json"
            first = save_discovery_sweep(report, latest)
            second = save_discovery_sweep(report, latest)
            history = list_versioned_discovery_sweeps(latest.parent / "discovery-sweeps")
            self.assertEqual([document["run_id"] for _, document in history],
                             [second["run_id"], first["run_id"]])
            history[0][0].write_text("{invalid", encoding="utf-8")
            remaining = list_versioned_discovery_sweeps(latest.parent / "discovery-sweeps")
            self.assertEqual([document["run_id"] for _, document in remaining],
                             [first["run_id"]])


if __name__ == "__main__":
    unittest.main()

