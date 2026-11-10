import unittest

from tools.serve_trained_lora import validate_budget


class TrainedLoraServerTests(unittest.TestCase):
    def test_generation_budget_has_a_hard_upper_bound(self):
        self.assertEqual(validate_budget(96), 96)
        self.assertEqual(validate_budget(512), 512)
        for invalid in (0, 31, 513, True, "96", None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_budget(invalid)


if __name__ == "__main__":
    unittest.main()

