import csv
import io
import unittest
from organism_lab.experiments import run_experiment, compare_control, to_csv

class ExperimentTests(unittest.TestCase):
    def test_history_length(self):
        self.assertEqual(len(run_experiment(steps=12)["history"]), 13)
    def test_reproducible(self):
        self.assertEqual(run_experiment(seed=5), run_experiment(seed=5))
    def test_csv_rows(self):
        rows = list(csv.DictReader(io.StringIO(to_csv(run_experiment(steps=3)))))
        self.assertEqual(len(rows), 4)
    def test_control(self):
        result = compare_control(steps=15, resources=30)
        self.assertLessEqual(result["control"]["final"]["population"], 1)
    def test_invalid_steps(self):
        with self.assertRaises(ValueError):
            run_experiment(steps=-1)
