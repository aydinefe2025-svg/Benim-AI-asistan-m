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
        self.assertEqual([row["arm"] for row in first["results"]],
                         ["mutation", "no_mutation", "reproduction_disabled"])
        self.assertEqual(len(first["paired_comparisons"]), 3)
        mutation_control = first["paired_comparisons"][0]
        self.assertEqual(mutation_control["paired_seeds"], 3)
        self.assertLessEqual(mutation_control["approx_ci95_low"],
                             mutation_control["approx_ci95_high"])
        self.assertEqual(first["design"]["interval_method"].split(";")[0],
                         "paired Student-t 95% interval")
        final_rows = [row for row in first["observations"] if row["tick"] == 30]
        no_mutation = [row for row in final_rows if row["arm"] == "no_mutation"]
        no_reproduction = [row for row in final_rows
                           if row["arm"] == "reproduction_disabled"]
        self.assertTrue(all(row["task_b_share"] == 0 for row in no_mutation))
        self.assertTrue(all(row["births"] == 0 for row in no_reproduction))
        self.assertEqual(first["design"]["shift_tick"], 10)
        self.assertIn("not an AI model", first["interpretation_limits"][0])

    def test_report_is_persisted_as_json(self):
        report = run_adaptation_study(seeds=(4, 5), steps=12, shift_tick=5, capacity=8)
        with tempfile.TemporaryDirectory() as tmp:
            path = save_adaptation_study(report, Path(tmp) / "nested" / "study.json")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), report)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_bounds_prevent_unbounded_runs(self):
        for kwargs in ({"seeds": (1,), "steps": 20, "shift_tick": 5},
                       {"seeds": (1, 2), "steps": 20, "shift_tick": 20},
                       {"seeds": (1, 2), "steps": 1001, "shift_tick": 20}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_adaptation_study(**kwargs)


if __name__ == "__main__":
    unittest.main()

