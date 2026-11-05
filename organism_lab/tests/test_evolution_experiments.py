import unittest
from organism_lab.evolution_experiments import run_experiment, compare_experiments


class EvolutionExperimentTests(unittest.TestCase):
    def test_reproducible(self):
        self.assertEqual(run_experiment(seed=42), run_experiment(seed=42))

    def test_population_and_lineage_accounting(self):
        for resources in (0, 2, 10, 50):
            result = run_experiment(seed=7, steps=200, capacity=12, resources=resources)
            self.assertEqual(len(result["history"]), 200)
            for row in result["history"]:
                self.assertGreaterEqual(row["population"], 0)
                self.assertLessEqual(row["population"], 12)
                self.assertEqual(row["population"], 1 + row["births"] - row["deaths"])

    def test_comparison(self):
        result = compare_experiments(seeds=(1, 2, 3), steps=30)
        self.assertEqual(result["runs"], 3)
        self.assertEqual(len(result["results"]), 3)

    def test_rejects_invalid_parameters(self):
        for kwargs in ({"steps": -1}, {"capacity": 0}, {"resources": -1},
                       {"steps": 10001}, {"seed": True}, {"capacity": 1.2}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_experiment(**kwargs)
        with self.assertRaises(ValueError):
            compare_experiments(seeds=(1, 1))


if __name__ == "__main__":
    unittest.main()
