#!/usr/bin/env python3
import os
import unittest
from pathlib import Path

from research.j0740.f118 import f118_intradensity_fixedj_scan as f118
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

class F118Preflight(unittest.TestCase):
    def test_source_pins_and_interior_density_ticks(self):
        self.assertEqual(f118.GRID, "2501x5001")
        self.assertEqual(f118.RHO_TICKS_1E9, (2622282, 2622285, 2622288))
        self.assertEqual(f118.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(f106.TARGET_J, 4.8245626795750385e48)
        self.assertEqual(f106.J_REL_TOL, 3e-5)

    def test_f117_and_nested_f116_baselines(self):
        result, rows, inner = f118.read_f117(Path(os.environ["F117_ARTIFACT_ZIP"]))
        self.assertEqual(result["status"], "F117_NEIGHBOR_DENSITY_FIXEDJ_ROOTS_COMPLETE")
        self.assertEqual(len(rows), 10)
        self.assertEqual(len(result["fixed_J_solutions"]), 2)
        self.assertEqual(inner["status"], "F116_FIFTH_GRID_FIXEDJ_ROOTS_COMPLETE")
        self.assertEqual([x["rho_tick_1e10_g_cm3"] for x in inner["fixed_J_solutions"]], [262228, 262229])

    def test_ratio_cache_and_no_overwrite(self):
        source = Path(f118.__file__).read_text()
        self.assertIn("if key not in cache", source)
        self.assertIn("NEVER_OVERWRITE_F118_RAW_FIXEDJ_JOURNAL", source)
        self.assertIn("baseline_linear", source)

    def test_claim_is_bounded(self):
        source = Path(f118.__file__).read_text()
        self.assertIn('"diagnostic_only": True', source)
        self.assertIn("do not establish", source)

if __name__ == "__main__":
    unittest.main()
