import unittest
from organism_lab.lineage import run_lineage, evaluate_improvement

class LineageTests(unittest.TestCase):
    def test_founder(self):
        r = run_lineage(steps=0)
        self.assertEqual(r["genealogy"][0]["parent"], None)
        self.assertEqual(r["ever_born"], 1)
    def test_descendants(self):
        r = run_lineage(seed=2, steps=15, resources=30)
        self.assertGreater(r["ever_born"], 1)
        self.assertTrue(all(entry["parent"] in r["genealogy"] for entry in r["genealogy"].values() if entry["parent"] is not None))
    def test_repeatable(self):
        self.assertEqual(run_lineage(seed=7), run_lineage(seed=7))
    def test_improvement_direction(self):
        self.assertEqual(evaluate_improvement({"founder_efficiency": 2, "final_mean_efficiency": 3})["direction"], "up")
    def test_invalid_steps(self):
        with self.assertRaises(ValueError):
            run_lineage(steps=-1)
