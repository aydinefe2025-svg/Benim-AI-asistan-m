import unittest
from organism_lab.runner import report

class RunnerValidationTests(unittest.TestCase):
    def test_boolean_steps_are_invalid(self):
        with self.assertRaises(ValueError):
            report(steps=True)

    def test_negative_steps_are_invalid(self):
        with self.assertRaises(ValueError):
            report(steps=-1)

    def test_zero_steps_are_supported(self):
        result = report(steps=0)
        self.assertEqual(result['parameters']['steps'], 0)
