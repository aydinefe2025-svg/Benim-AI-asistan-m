import csv
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from organism_lab.reproduction_study import run_study, save_study, summarize_with_local_model


class ReproductionStudyTests(unittest.TestCase):
    def test_paired_study_is_reproducible_and_keeps_raw_observations(self):
        first = run_study(seeds=(0, 1, 2), steps=10, resource_levels=(0, 8))
        second = run_study(seeds=(0, 1, 2), steps=10, resource_levels=(0, 8))
        self.assertEqual(first, second)
        self.assertEqual(len(first["observations"]), 6)
        self.assertEqual(first["observations"][0]["control_population"], 0)
        self.assertEqual(first["results"][0]["paired_population_difference"]["ci95_low"], 0)

    def test_storage_writes_json_csv_and_sqlite_record(self):
        report = run_study(seeds=(1, 2), steps=5, resource_levels=(0, 3))
        with tempfile.TemporaryDirectory() as tmp:
            paths = save_study(report, tmp, model_commentary={"status": "test", "text": "local note"})
            saved = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["results"], report["results"])
            with Path(paths["csv_path"]).open(encoding="utf-8", newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 4)
            connection = sqlite3.connect(paths["database_path"])
            try:
                row = connection.execute("SELECT study_id, report_json FROM studies").fetchone()
            finally:
                connection.close()
            self.assertEqual(row[0], paths["study_id"])
            self.assertEqual(json.loads(row[1])["schema"], report["schema"])

    def test_rejects_bad_or_unbounded_parameters(self):
        for kwargs in (
            {"seeds": (0,), "steps": 10, "resource_levels": (0, 1)},
            {"seeds": (0, 1), "steps": 1001, "resource_levels": (0, 1)},
            {"seeds": (0, 1), "steps": 10, "resource_levels": (0,)},
            {"seeds": (True, 1), "steps": 10, "resource_levels": (0, 1)},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_study(**kwargs)

    def test_rejects_local_model_check_that_contradicts_zero_resource_result(self):
        report = run_study(seeds=(0, 1), steps=10, resource_levels=(0, 8))
        wrong = {"checks": [
            {"resource_per_tick": 0, "interval_contains_zero": False,
             "mean_difference_positive": False},
            {"resource_per_tick": 8, "interval_contains_zero": False,
             "mean_difference_positive": True},
        ]}
        with patch("organism_lab.reproduction_study.generate",
                   return_value={"provider": "ollama", "text": json.dumps(wrong)}):
            result = summarize_with_local_model(report)
        self.assertEqual(result["status"], "rejected_inconsistent")
        self.assertNotIn("checks", result)

    def test_accepts_structured_local_model_metric_check(self):
        report = run_study(seeds=(0, 1), steps=10, resource_levels=(0, 8))
        checks = []
        for row in report["results"]:
            interval = row["paired_population_difference"]
            checks.append({"resource_per_tick": row["resource_per_tick"],
                           "interval_contains_zero": interval["ci95_low"] <= 0 <= interval["ci95_high"],
                           "mean_difference_positive": interval["mean"] > 0})
        with patch("organism_lab.reproduction_study.generate",
                   return_value={"provider": "ollama", "text": json.dumps({"checks": checks})}):
            result = summarize_with_local_model(report)
        self.assertEqual(result["status"], "metric_consistent")
        self.assertEqual(result["checks"], checks)


if __name__ == "__main__":
    unittest.main()
