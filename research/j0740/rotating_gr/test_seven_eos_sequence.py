"""Offline tests for seven-source-EOS stable-branch safeguards."""
from __future__ import annotations
import unittest
import tempfile
from pathlib import Path
import numpy as np

from seven_eos_sequence import EOS_NAMES, first_stable_crossing, stable_source_radius_at_mass


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
        self.assertIsNone(first_stable_crossing(points, 2.12))

    def test_density_duplicates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate central density"):
            first_stable_crossing([mock(1e15, 1.9), mock(1e15, 2.1)], 2.073)

    def test_bad_mass_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "invalid target"):
            first_stable_crossing([mock(1e15, 2)], float("nan"))


class StableSourceReferenceTests(unittest.TestCase):
    def write_npz(self, path, masses, radii):
        np.savez(path, masses_EOS=np.asarray(masses),
                 radii_EOS=np.asarray(radii))

    def test_preserves_ascending_branch_and_discards_unstable_extension(self):
        masses=np.array([0.7+i*0.13 for i in range(13)] + [2.24, 2.20])
        radii=np.linspace(12.2, 9.9, len(masses))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"WFF1.npz"
            self.write_npz(p,masses,radii)
            radius,meta=stable_source_radius_at_mass(p, 2.073)
            self.assertTrue(9 < radius < 12.3)
            self.assertEqual(meta["discarded_post_maximum_nodes"], 2)
            self.assertEqual(meta["first_maximum_index"], 12)

    def test_nonmonotone_before_mass_peak_is_not_sorted_away(self):
        masses=np.array([0.7, 0.85, 1., 1.15, 1.30, 1.45, 1.55,
                         1.54, 1.70, 1.85, 2., 2.15, 2.3])
        radii=np.linspace(12,10,len(masses))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"WFF1.npz"
            self.write_npz(p,masses,radii)
            with self.assertRaisesRegex(ValueError,"nonmonotone"):
                stable_source_radius_at_mass(p, 2.073)

    def test_original_order_low_mass_turnback_is_excluded(self):
        # Matches the source-data diagnosis: APR4_EPP and WFF1 first
        # descend to a minimum then strictly increase through M=2.073.
        masses=np.r_[[.5,.3,.2,.1], np.linspace(.13,2.15,32)]
        radii=np.linspace(15.0,10.0,len(masses))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"APR4_EPP.npz"
            self.write_npz(p,masses,radii)
            radius,meta=stable_source_radius_at_mass(p,2.073)
            self.assertTrue(10 < radius < 15)
            self.assertEqual(meta["source_mass_minimum_index"],3)
            self.assertEqual(meta["discarded_pre_minimum_nodes"],3)
            self.assertEqual(meta["discarded_post_maximum_nodes"],0)

    def test_low_mass_source_prefix_must_be_strictly_descending(self):
        masses=np.r_[[.5,.3,.4,.1],np.linspace(.13,2.15,32)]
        radii=np.linspace(15.0,10.0,len(masses))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"APR4_EPP.npz"
            self.write_npz(p,masses,radii)
            with self.assertRaisesRegex(ValueError,"nonmonotone"):
                stable_source_radius_at_mass(p,2.073)

    def test_no_target_extrapolation(self):
        masses=np.linspace(0.7, 2.1, 20)
        radii=np.linspace(12,10,20)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"WFF1.npz"
            self.write_npz(p,masses,radii)
            with self.assertRaisesRegex(ValueError,"outside"):
                stable_source_radius_at_mass(p, 2.3)


if __name__ == "__main__":
    unittest.main()
