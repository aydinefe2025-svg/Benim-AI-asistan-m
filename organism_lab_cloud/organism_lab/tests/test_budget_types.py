import unittest
from organism_lab.shared_world import Budget, run_shared_world

class BudgetTypeTests(unittest.TestCase):
    def test_boolean_budget_rejected(self):
        with self.assertRaises(ValueError):
            Budget(True, 1)
    def test_boolean_spend_rejected(self):
        with self.assertRaises(ValueError):
            Budget(4, 4).spend(energy=True)
    def test_fractional_grid_rejected(self):
        with self.assertRaises(ValueError):
            run_shared_world(width=2.5)
    def test_boolean_steps_rejected(self):
        with self.assertRaises(ValueError):
            run_shared_world(steps=True)

