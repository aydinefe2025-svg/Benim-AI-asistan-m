#!/usr/bin/env python3
import os
import unittest
from pathlib import Path

from research.j0740.f108 import f108_fixed_j_fine_density_probe as f108


class F108Preflight(unittest.TestCase):
    def test_density_plan_reuses_old_points_without_duplicate_c_calls(self):
        self.assertEqual(len(f108.SCAN_TICKS), 31)
        self.assertEqual(len(f108.RHO), 28)
        self.assertEqual(set(f108.SCAN_TICKS) & f108.REUSE_TICKS, f108.REUSE_TICKS)
        self.assertEqual(len(set(f108.SCAN_TICKS)), len(f108.SCAN_TICKS))

    def test_fixed_j_physics_and_f99_lock(self):
        self.assertEqual(f108.GRID, "501x1001")
        self.assertEqual(f108.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(f108.f106.TARGET_J, 4.8245626795750385e48)
        self.assertEqual(f108.f106.J_REL_TOL, 3e-5)

    def test_prior_f107_artifact_raw_trace_and_reused_points(self):
        result, rows, _ = f108.read_f107(Path(os.environ["F107_ARTIFACT_ZIP"]))
        self.assertEqual(result["status"], "DENSE_LOCAL_SCAN_PASS")
        self.assertEqual(len(rows), 138)
        self.assertEqual(len(result["combined_local_samples_with_F106_reference"]), 21)

    def test_result_cannot_claim_peak_or_science_completion(self):
        source = Path(f108.__file__).read_text()
        self.assertIn("does not certify a unique physical maximum", source)
        self.assertIn("UNRESOLVED_BY_THIS_SCAN", source)
        self.assertIn('"diagnostic_only": True', source)


if __name__ == "__main__":
    unittest.main()
