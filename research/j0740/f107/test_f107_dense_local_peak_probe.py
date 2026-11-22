#!/usr/bin/env python3
import os
import unittest
from pathlib import Path
from research.j0740.f107 import f107_dense_local_peak_probe as f107
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

class F107Preflight(unittest.TestCase):
    def test_locked_physics_and_mesh(self):
        self.assertEqual(f107.GRID, "501x1001")
        self.assertEqual(f106.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(f106.TARGET_J, 4.8245626795750385e48)
        self.assertEqual(f106.J_REL_TOL, 3e-5)

    def test_dense_scan_has_no_repeated_f106_density(self):
        self.assertEqual(len(f107.RHO), 14)
        self.assertTrue(all(f107.RHO[i] < f107.RHO[i+1] for i in range(len(f107.RHO)-1)))
        self.assertFalse(set(f107.RHO).intersection(set(f106.RHO)))

    def test_f106_receipt_and_its_raw_c_rows(self):
        result = f107.read_f106(Path(os.environ["F106_ARTIFACT_ZIP"]))
        self.assertEqual(result["status"], "SIXTH_MESH_LOCAL_SAMPLED_TURN_PASS")
        self.assertEqual(len(result["new_native_C_stars"]), 7)
        self.assertEqual(result["new_native_C_call_count"], 70)

    def test_older_pinned_baselines_remain_valid(self):
        prior3, base = f106.read_baseline(Path(os.environ["F103_ARTIFACT_ZIP"]))
        prior4 = f106.read_f104(Path(os.environ["F104_ARTIFACT_ZIP"]))
        prior5 = f106.read_f105_failed(Path(os.environ["F105_ARTIFACT_ZIP"]))
        self.assertEqual(len(prior3["new_native_C_stars"]), 7)
        self.assertEqual(len(prior4["new_native_C_stars"]), 7)
        self.assertEqual(prior5["status"], "FAIL_CLOSED")
        self.assertEqual(sum(len(v["stars"]) for v in base["both_native_C_grids"].values()), 28)

    def test_finite_grid_claim_is_limited(self):
        source = Path(f107.__file__).read_text()
        self.assertIn("does not establish continuum/grid convergence", source.lower())
        self.assertIn('"-r"', Path(f106.__file__).read_text())
        self.assertNotIn('"-s"', Path(f106.__file__).read_text())

if __name__ == "__main__":
    unittest.main()
