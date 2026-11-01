"""Regression checks for resource limits and edge-case inputs."""
import unittest
from organism_lab.shared_world import run_shared_world

class SharedWorldBoundaryTests(unittest.TestCase):
    def test_zero_steps_keeps_initial_budget(self):
        result = run_shared_world(steps=0, energy=17, materials=9)
        self.assertEqual(result["history"], [])
        self.assertEqual((result["energy_left"], result["materials_left"]), (17, 9))
        self.assertEqual((result["robots"], result["organisms"]), (0, 1))

    def test_zero_resources_never_builds_or_births(self):
        result = run_shared_world(steps=100, energy=0, materials=0)
        self.assertEqual((result["robots"], result["organisms"], result["successful_routes"]), (0, 1, 0))
        self.assertEqual(len(result["history"]), 100)

    def test_large_step_count_stays_bounded(self):
        result = run_shared_world(steps=10000, energy=40, materials=12)
        self.assertEqual(len(result["history"]), 10000)
        self.assertLessEqual(result["organisms"], 32)
        self.assertTrue(all(row["energy_left"] >= 0 and row["materials_left"] >= 0 for row in result["history"]))

    def test_boolean_resources_rejected(self):
        for key in ("energy", "materials"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                run_shared_world(**{key: True})

    def test_repeated_runs_are_identical(self):
        settings = dict(steps=40, energy=200, materials=80)
        self.assertEqual(run_shared_world(**settings), run_shared_world(**settings))

if __name__ == "__main__":
    unittest.main()
