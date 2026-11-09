import json
import tempfile
import unittest
from pathlib import Path

from organism_lab.adaptation_study import run_adaptation_study, save_adaptation_study


class AdaptationStudyTests(unittest.TestCase):
    def test_seeded_environment_shift_is_repeatable_and_paired(self):
        args = dict(seeds=(1, 2, 3), steps=30, shift_tick=10, capacity=16)
        first = run_adaptation_study(**args)
        self.assertEqual(first, run_adaptation_study(**args))
        self.assertEqual(len(first["observations"]), 3 * 3 * 30)
        self.assertEqual([row["arm"] for row in first["results"]], ["mutation", "no_mutation", "no_reproduction"])
        self.assertEqual(first["design"]["shift_tick"], 10)
        self.assertIn("not an AI model", first["interpretation_limits"][0])
        final_rows = [row for row in first["observations"] if row["tick"] == 30]
        self.assertTrue(all("births_this_tick" in row and "deaths_this_tick" in row
                            for row in final_rows))
        self.assertTrue(all(row["fitness_distribution_by_generation"]
                            for row in final_rows))


    def test_no_reproduction_is_a_negative_control_and_paired_intervals_are_reported(self):
        report = run_adaptation_study(seeds=tuple(range(20)), steps=30,
                                      shift_tick=10, capacity=16)
        no_reproduction = next(row for row in report["results"]
                               if row["arm"] == "no_reproduction")
        self.assertEqual(no_reproduction["final_population_mean"], 1)
        self.assertEqual(no_reproduction["final_task_b_share_mean"], 0)
        self.assertEqual(no_reproduction["adapted_seed_rate"], 0)
        self.assertEqual(no_reproduction["paired_seeds"], 20)
        differences = report["paired_task_b_share_differences_mutation_minus_controls"]
        self.assertIn("met", report["adaptation_criterion"])
        self.assertIn("adaptation_acceptance_criterion", report["design"])
        for control in ("no_mutation", "no_reproduction"):
            self.assertIsNotNone(differences[control]["ci95_low"])
            self.assertLessEqual(differences[control]["ci95_low"],
                                 differences[control]["mean"])
            self.assertLessEqual(differences[control]["mean"],
                                 differences[control]["ci95_high"])

    def test_report_is_persisted_as_json(self):
        report = run_adaptation_study(seeds=(4, 5), steps=12, shift_tick=5, capacity=8)
        with tempfile.TemporaryDirectory() as tmp:
            path = save_adaptation_study(report, Path(tmp) / "nested" / "study.json")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), report)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_save_is_idempotent_and_never_overwrites_different_experiment(self):
        first = run_adaptation_study(seeds=(4, 5), steps=12, shift_tick=5, capacity=8)
        second = run_adaptation_study(seeds=(6, 7), steps=12, shift_tick=5, capacity=8)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reports" / "study.json"
            self.assertEqual(save_adaptation_study(first, path), path)
            original_bytes = path.read_bytes()
            self.assertEqual(save_adaptation_study(first, path), path)
            self.assertEqual(path.read_bytes(), original_bytes)
            with self.assertRaises(FileExistsError):
                save_adaptation_study(second, path)
            self.assertEqual(path.read_bytes(), original_bytes)

    def test_bounds_prevent_unbounded_runs(self):
        for kwargs in ({"seeds": (1,), "steps": 20, "shift_tick": 5},
                       {"seeds": (1, 2), "steps": 20, "shift_tick": 20},
                       {"seeds": (1, 2), "steps": 1001, "shift_tick": 20}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_adaptation_study(**kwargs)


if __name__ == "__main__":
    unittest.main()

