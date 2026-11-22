#!/usr/bin/env python3
import os
import unittest
from pathlib import Path

from research.j0740.f114 import f114_third_grid_fixedj_roots as f114
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

class F114Preflight(unittest.TestCase):
    def test_third_mesh_and_fixed_j_inputs(self):
        self.assertEqual(f114.PREVIOUS_GRID, "1001x2001")
        self.assertEqual(f114.GRID, "1501x3001")
        self.assertEqual(f114.RHO_TICKS_1E10, (262228, 262229))
        self.assertEqual(f114.RATIO_SCAN, (0.999, 0.995, 0.990))
        self.assertEqual(f114.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(f106.TARGET_J, 4.8245626795750385e48)
        self.assertEqual(f106.J_REL_TOL, 3e-5)

    def test_f113_artifact_checksum_and_prior_roots(self):
        result, rows = f114.read_f113(Path(os.environ["F113_ARTIFACT_ZIP"]))
        self.assertEqual(result["status"], "F113_HIGH_GRID_FIXEDJ_ROOTS_COMPLETE")
        self.assertEqual(len(rows), 14)
        self.assertEqual(len(result["fixed_J_solutions"]), 2)

    def test_cache_and_raw_journal_guard(self):
        source = Path(f114.__file__).read_text()
        self.assertIn("if key not in cache", source)
        self.assertIn("NEVER_OVERWRITE_F114_RAW_FIXEDJ_JOURNAL", source)

    def test_two_grid_comparison_is_not_continuum_acceptance(self):
        source = Path(f114.__file__).read_text()
        self.assertIn('"diagnostic_only": True', source)
        self.assertIn("still not continuum convergence", source)
        self.assertIn("cannot establish branch identity", source)

if __name__ == "__main__":
    unittest.main()
