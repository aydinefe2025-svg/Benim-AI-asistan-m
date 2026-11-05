import unittest
from organism_lab.population_study import trial, resource_sweep

class PopulationStudyTests(unittest.TestCase):
    def test_repeatable(self):
        self.assertEqual(trial(), trial())
    def test_seed_count(self):
        self.assertEqual(len(trial(seeds=(5, 6))["trials"]), 2)
    def test_diversity_bounded(self):
        self.assertTrue(all(0 <= r["diversity"] <= 4 for r in trial()["trials"]))
    def test_no_resource_survival(self):
        self.assertEqual(trial(seeds=(0,), resources=0)["mean_population"], 0)
    def test_sweep(self):
        self.assertEqual(len(resource_sweep(resource_levels=(0, 10))), 2)
    def test_empty_seeds(self):
        with self.assertRaises(ValueError):
            trial(seeds=())
