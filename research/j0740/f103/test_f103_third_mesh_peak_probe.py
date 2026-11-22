#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("f103", ROOT / "f103_third_mesh_peak_probe.py")
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)

class F103Preflight(unittest.TestCase):
    def test_fixed_physics_and_strict_acceptance_preserved(self):
        self.assertEqual(F.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(F.TARGET_J, 4.8245626795750385e48)
        self.assertEqual(F.J_REL_TOL, 3e-5)

    def test_third_mesh_is_distinct_and_local_density_scan_brackets_old_peaks(self):
        self.assertEqual(F.GRID, "251x501")
        self.assertEqual(len(F.RHO), 7)
        self.assertTrue(all(F.RHO[i] < F.RHO[i+1] for i in range(len(F.RHO)-1)))
        self.assertLess(F.RHO[0], 2.76e15)
        self.assertGreater(F.RHO[-1], 2.82e15)

    def test_direct_native_ratio_path_does_not_use_SetSpin(self):
        source = (ROOT / "f103_third_mesh_peak_probe.py").read_text()
        self.assertIn('"-r"', source)
        self.assertNotIn('"-s"', source)
        self.assertIn("real_native_RNS_C", source)

    def test_no_full_science_claim(self):
        source = (ROOT / "f103_third_mesh_peak_probe.py").read_text()
        self.assertIn("do not prove a continuous turning point", source.lower())

if __name__ == "__main__":
    unittest.main()
