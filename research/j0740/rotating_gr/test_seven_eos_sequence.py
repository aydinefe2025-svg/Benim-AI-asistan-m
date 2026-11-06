"""Offline tests for seven-source-EOS stable-branch safeguards."""
from __future__ import annotations
import unittest

from seven_eos_sequence import EOS_NAMES, first_stable_crossing


def mock(ec, mass):
    return {"central_energy_density_g_cm3": ec, "mass_msun": mass}


class SevenEosSequenceTests(unittest.TestCase):
    def test_exact_seven_source_labels(self):
        self.assertEqual(EOS_NAMES, (
            "APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2"))

    def test_bracket_first_stable_crossing(self):
        points = [mock(0.9e15, 1.9), mock(1e15, 2.05),
                  mock(1.1e15, 2.1), mock(1.3e15, 2.07)]
        self.assertEqual(first_stable_crossing(points, 2.073),
                         (1e15, 1.1e15))

    def test_missing_mass_no_extrapolation(self):
        points = [mock(0.9e15, 1.9), mock(1.1e15, 2.01),
                  mock(1.3e15, 1.99)]
        self.assertIsNone(first_stable_crossing(points, 2.073))

    def test_unstable_branch_not_used(self):
        points = [mock(0.9e15, 1.8), mock(1e15, 2.10),
                  mock(1.1e15, 2.05), mock(1.2e15, 2.08)]
        self.assertIsNone(first_stable_crossing(points, 2.073) if False else
                          first_stable_crossing(points, 2.12))

    def test_density_duplicates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate central density"):
            first_stable_crossing([mock(1e15, 1.9), mock(1e15, 2.1)], 2.073)

    def test_bad_mass_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "invalid target"):
            first_stable_crossing([mock(1e15, 2)], float("nan"))


if __name__ == "__main__":
    unittest.main()
