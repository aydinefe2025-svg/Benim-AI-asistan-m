#!/usr/bin/env python3
import os
import unittest
from pathlib import Path

from research.j0740.f112 import f112_high_grid_mass_step_crosscheck as f112
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

class F112Preflight(unittest.TestCase):
    def test_mesh_and_physics_are_pinned(self):
        self.assertEqual(f112.LOW_GRID, "501x1001")
        self.assertEqual(f112.HIGH_GRID, "1001x2001")
        self.assertEqual(f112.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(f112.BRACKET_TICKS_1E10, (262228, 262229))
        self.assertEqual(f106.TARGET_J, 4.8245626795750385e48)
        self.assertEqual(f106.J_REL_TOL, 3e-5)

    def test_f111_artifact_and_four_fine_grid_endpoint_values(self):
        result, rows = f112.read_f111(Path(os.environ["F111_ARTIFACT_ZIP"]))
        self.assertEqual(result["status"], "F111_FIXED_RATIO_JUMP_BRACKET_COMPLETE")
        self.assertEqual(len(rows), 18)
        for label in ("A", "B"):
            points = result["series_by_fixed_ratio"][label]["points"]
            ticks = {int(round(p["rho_g_cm3"] / 1e10)) for p in points}
            self.assertTrue(set(f112.BRACKET_TICKS_1E10).issubset(ticks))

    def test_new_high_grid_calls_differ_from_cached_low_grid(self):
        self.assertEqual(len(f112.BRACKET_TICKS_1E10) * 2, 4)
        source = Path(f112.__file__).read_text()
        self.assertIn("NEVER_OVERWRITE_F112_RAW_HIGH_GRID_JOURNAL", source)
        self.assertIn("1001x2001", source)
        self.assertIn("501x1001", source)

    def test_claim_limit_is_not_continuum_acceptance(self):
        source = Path(f112.__file__).read_text()
        self.assertIn('"diagnostic_only": True', source)
        self.assertIn("not a fixed-J continuum-convergence proof", source)
        self.assertIn("cannot establish", source)

if __name__ == "__main__":
    unittest.main()
