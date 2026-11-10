import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core.virtual_generation import _confirmation_seeds, _paired_summary, run_virtual_generation


class VirtualGenerationTests(unittest.TestCase):
    def test_learning_gate_requires_positive_paired_interval(self):
        self.assertTrue(_paired_summary([1.0] * 4, [0.0] * 4)["positive_evidence"])
        self.assertFalse(_paired_summary([0.5, 0.0, 0.5, 0.0], [0.0] * 4)["positive_evidence"])

    def test_small_sample_uses_student_t_interval_and_rotation_uses_fresh_holdouts(self):
        summary = _paired_summary([0.0, 0.0, 1.0, 1.0], [0.0] * 4)
        # df=3 uses t(0.975)=3.182, wider than the normal approximation 1.96.
        self.assertLess(summary["ci95_low"], 0.0)
        self.assertNotEqual(_confirmation_seeds(1), _confirmation_seeds(2))
        self.assertEqual(len(set(_confirmation_seeds(1))), 12)

    def test_generation_is_bounded_persisted_readable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "colony.sqlite3"
            first = run_virtual_generation(database, 1)
            replay = run_virtual_generation(database, 1)
            self.assertEqual(first, replay)
            self.assertEqual(first["offspring_scope"], "bounded toy digital VM only")
            self.assertFalse(first["model_weights_updated"])
            self.assertIn(first["lesson_status"], {"transferred", "rejected"})
            self.assertGreater(first["training"]["candidate_mean_births"], 0)
            self.assertGreater(first["training"]["candidate_mean_max_generation"], 0)
            self.assertIn(first["primary_metric"], {
                "held-out task-B genome share",
                "final surviving unique genome count",
            })
            if first["lesson_status"] == "transferred":
                self.assertTrue(first["training"]["positive_evidence"])
                self.assertTrue(first["held_out_confirmation"]["positive_evidence"])
                self.assertEqual(first["next_generation_mutation_rate"], first["candidate_mutation_rate"])
            else:
                self.assertEqual(first["next_generation_mutation_rate"], first["parent_mutation_rate"])
            second = run_virtual_generation(database, 2)
            self.assertEqual(second["parent_generation_id"], 1)
            self.assertNotEqual(first["held_out_confirmation"]["seed_ids"],
                                second["held_out_confirmation"]["seed_ids"])
            with closing(sqlite3.connect(database)) as db, db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                row = db.execute("SELECT lesson_status,training_json,confirmation_json FROM virtual_generation WHERE tick_id=1").fetchone()
            self.assertEqual(row[0], first["lesson_status"])
            self.assertEqual(json.loads(row[1]), first["training"])
            self.assertEqual(json.loads(row[2]), first["held_out_confirmation"])


if __name__ == "__main__":
    unittest.main()
