#!/usr/bin/env python3
import os
import unittest
from pathlib import Path

from research.j0740.f113 import f113_fixedj_high_grid_roots as f113
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

class F113Preflight(unittest.TestCase):
    def test_high_grid_and_fixed_j_inputs(self):
        self.assertEqual(f113.GRID, "1001x2001")
        self.assertEqual(f113.RHO_TICKS_1E10, (262228, 262229))
        self.assertEqual(f113.RATIO_SCAN, (0.999, 0.995, 0.990))
        self.assertEqual(f113.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(f106.TARGET_J, 4.8245626795750385e48)
        self.assertEqual(f106.J_REL_TOL, 3e-5)

    def test_f112_artifact_hash_and_prior_high_grid_points(self):
        result, rows = f113.read_f112(Path(os.environ["F112_ARTIFACT_ZIP"]))
        self.assertEqual(result["status"], "F112_HIGH_GRID_CROSSCHECK_COMPLETE")
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["mesh"] == f113.GRID for row in rows))

    def test_cached_ratio_evaluation_avoids_duplicate_native_calls(self):
        source = Path(f113.__file__).read_text()
        self.assertIn("if key not in cache", source)
        self.assertIn("NEVER_OVERWRITE_F113_RAW_FIXEDJ_JOURNAL", source)

    def test_claim_limit_is_bounded(self):
        source = Path(f113.__file__).read_text()
        self.assertIn('"diagnostic_only": True', source)
        self.assertIn("do not prove branch identity", source)
        self.assertIn("global physical", source)

if __name__ == "__main__":
    unittest.main()
