#!/usr/bin/env python3
import os
import unittest
from pathlib import Path

from research.j0740.f110 import f110_fixed_ratio_density_scan as f110
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

class F110Preflight(unittest.TestCase):
    def test_immutable_physics_and_density_plan(self):
        self.assertEqual(f110.GRID, "501x1001")
        self.assertEqual(f110.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(f110.INTERIOR_RHO_TICKS_1E11, tuple(range(26221, 26230)))
        self.assertEqual(len(f110.INTERIOR_RHO_TICKS_1E11), 9)
        self.assertEqual(f106.TARGET_J, 4.8245626795750385e48)
        self.assertEqual(f106.J_REL_TOL, 3e-5)

    def test_f108_f109_baselines_and_four_endpoint_matrix(self):
        r108, r109, ratios, endpoints = f110.load_baselines(
            Path(os.environ["F108_ARTIFACT_ZIP"]),
            Path(os.environ["F109_ARTIFACT_ZIP"]),
        )
        self.assertEqual(r108["status"], "F108_NATIVE_C_FINE_SCAN_PASS")
        self.assertEqual(r109["status"], "F109_CROSS_RATIO_NATIVE_C_COMPLETE")
        self.assertEqual(len(endpoints["A"]), 2)
        self.assertEqual(len(endpoints["B"]), 2)
        self.assertNotEqual(ratios["A"], ratios["B"])
        self.assertEqual(
            {row["rho_tick_1e11_g_cm3"] for row in endpoints["A"]},
            {26220, 26230},
        )

    def test_only_interior_points_are_new(self):
        ticks = set(f110.INTERIOR_RHO_TICKS_1E11)
        self.assertEqual(len(ticks), 9)
        self.assertNotIn(26220, ticks)
        self.assertNotIn(26230, ticks)
        self.assertEqual(2 * len(ticks), 18)

    def test_claim_limit_and_duplicate_journal_guard(self):
        source = Path(f110.__file__).read_text()
        self.assertIn("NEVER_OVERWRITE_F110_RAW_DENSITY_JOURNAL", source)
        self.assertIn('"diagnostic_only": True', source)
        self.assertIn("not a fixed-J sequence at interior densities", source)
        self.assertIn("cannot prove", source)

if __name__ == "__main__":
    unittest.main()
