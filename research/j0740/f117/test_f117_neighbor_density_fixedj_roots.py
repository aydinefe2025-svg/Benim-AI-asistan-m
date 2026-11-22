#!/usr/bin/env python3
import os
import unittest
from pathlib import Path

from research.j0740.f117 import f117_neighbor_density_fixedj_roots as f117
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

class F117Preflight(unittest.TestCase):
    def test_fifth_grid_and_fixed_j_inputs(self):
        self.assertEqual(f117.PREVIOUS_GRID, "2501x5001")
        self.assertEqual(f117.GRID, "2501x5001")
        self.assertEqual(f117.RHO_TICKS_1E10, (262227, 262230))
        self.assertEqual(f117.RATIO_BRACKET_HALF_WIDTH, 2.5e-5)
        self.assertEqual(f117.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(f106.TARGET_J, 4.8245626795750385e48)
        self.assertEqual(f106.J_REL_TOL, 3e-5)

    def test_f116_baseline_and_previous_roots(self):
        result, rows = f117.read_f116(Path(os.environ["F116_ARTIFACT_ZIP"]))
        self.assertEqual(result["status"], "F116_FIFTH_GRID_FIXEDJ_ROOTS_COMPLETE")
        self.assertEqual(len(rows), 10)
        self.assertEqual(len(result["fixed_J_solutions"]), 2)

    def test_ratio_cache_prevents_duplicate_c_calls(self):
        source = Path(f117.__file__).read_text()
        self.assertIn("if key not in cache", source)
        self.assertIn("NEVER_OVERWRITE_F117_RAW_FIXEDJ_JOURNAL", source)

    def test_limited_claim_and_local_brackets(self):
        source = Path(f117.__file__).read_text()
        self.assertIn('"diagnostic_only": True', source)
        self.assertIn("local_ratio_bracket", source)
        self.assertIn("does not establish", source)

if __name__ == "__main__":
    unittest.main()
