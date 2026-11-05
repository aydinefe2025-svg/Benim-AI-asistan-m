import unittest
from organism_lab.battery_twin import synthetic_line, evaluate

class BatteryTwinTests(unittest.TestCase):
    def test_repeatable(self):
        self.assertEqual(synthetic_line(), synthetic_line())
    def test_metrics_count(self):
        result = evaluate(synthetic_line(samples=100))
        self.assertEqual(sum(result[k] for k in ("true_positive", "false_positive",
                         "false_negative", "true_negative")), 100)
    def test_energy_positive(self):
        self.assertTrue(all(row["energy_kwh"] > 0 for row in synthetic_line()))
    def test_invalid_samples(self):
        with self.assertRaises(ValueError):
            synthetic_line(samples=1)
    def test_empty(self):
        with self.assertRaises(ValueError):
            evaluate([])
    def test_no_claim_of_real_validation(self):
        self.assertIn("Synthetic", evaluate(synthetic_line())["warning"])
