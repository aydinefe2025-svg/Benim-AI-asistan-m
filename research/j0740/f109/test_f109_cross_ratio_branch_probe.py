#!/usr/bin/env python3
import os
import unittest
from pathlib import Path

from research.j0740.f109 import f109_cross_ratio_branch_probe as f109
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

class F109Preflight(unittest.TestCase):
    def test_exact_inputs_and_two_density_plan(self):
        self.assertEqual(f109.GRID, "501x1001")
        self.assertEqual(f109.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(f109.CROSS_DENSITY_TICKS, (2622, 2623))
        self.assertEqual(f106.TARGET_J, 4.8245626795750385e48)
        self.assertEqual(f106.J_REL_TOL, 3e-5)

    def test_f108_checksum_and_raw_source_roots(self):
        result, rows, stars = f109.read_f108(Path(os.environ["F108_ARTIFACT_ZIP"]))
        self.assertEqual(result["status"], "F108_NATIVE_C_FINE_SCAN_PASS")
        self.assertEqual(len(rows), 280)
        self.assertEqual(len(stars), 28)
        self.assertIn(2622, stars)
        self.assertIn(2623, stars)

    def test_only_two_nonrepeat_cross_density_calls_are_planned(self):
        self.assertEqual(len(f109.CROSS_DENSITY_TICKS), 2)
        source = Path(f109.__file__).read_text()
        self.assertIn("density_2622_with_ratio_selected_at_2623", source)
        self.assertIn("density_2623_with_ratio_selected_at_2622", source)
        self.assertIn("NEVER_OVERWRITE_F109_RAW_CROSS_PROBE_JOURNAL", source)

    def test_diagnostic_cannot_claim_scientific_completion(self):
        source = Path(f109.__file__).read_text()
        self.assertIn('"diagnostic_only": True', source)
        self.assertIn("It cannot prove", source)
        self.assertIn("F109_CROSS_RATIO_NATIVE_C_COMPLETE", source)

if __name__ == "__main__":
    unittest.main()
