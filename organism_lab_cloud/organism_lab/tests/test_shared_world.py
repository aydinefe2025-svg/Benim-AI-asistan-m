import unittest
from organism_lab.shared_world import Budget, run_shared_world

class SharedWorldTests(unittest.TestCase):
    def test_atomic_budget(self):
        b = Budget(5, 2)
        self.assertFalse(b.spend(energy=6, materials=1))
        self.assertEqual((b.energy, b.materials), (5, 2))
    def test_budget_consumption(self):
        b = Budget(5, 2)
        self.assertTrue(b.spend(energy=2, materials=1))
        self.assertEqual((b.energy, b.materials), (3, 1))
    def test_no_negative_resources(self):
        r = run_shared_world(steps=20, energy=15, materials=4)
        self.assertGreaterEqual(r["energy_left"], 0)
        self.assertGreaterEqual(r["materials_left"], 0)
    def test_no_budget(self):
        r = run_shared_world(energy=0, materials=0)
        self.assertEqual(r["robots"], 0)
        self.assertEqual(r["births"], 0)
    def test_repeatable(self):
        self.assertEqual(run_shared_world(), run_shared_world())
    def test_route_success(self):
        self.assertGreater(run_shared_world(steps=1, energy=20, materials=4)["successful_routes"], 0)
    def test_invalid_cost(self):
        with self.assertRaises(ValueError):
            Budget(5, 5).spend(energy=-1)

