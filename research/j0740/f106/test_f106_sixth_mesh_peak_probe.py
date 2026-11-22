#!/usr/bin/env python3
import importlib.util
import os
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("f106",ROOT/"f106_sixth_mesh_peak_probe.py")
F=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(F)

class F106Preflight(unittest.TestCase):
    def test_fixed_inputs_and_tolerance(self):
        self.assertEqual(F.GRID,"501x1001")
        self.assertEqual(F.EOS_SHA,"c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(F.TARGET_J,4.8245626795750385e48)
        self.assertEqual(F.J_REL_TOL,3e-5)
    def test_local_density_scan_is_seven_points(self):
        self.assertEqual(len(F.RHO),7)
        self.assertTrue(all(F.RHO[i]<F.RHO[i+1] for i in range(6)))
    def test_pinned_f103_baseline_and_journal(self):
        path=Path(os.environ["F103_ARTIFACT_ZIP"])
        prior,base=F.read_baseline(path)
        self.assertEqual(len(prior["new_native_C_stars"]),7)
        self.assertEqual(sum(len(v["stars"]) for v in base["both_native_C_grids"].values()),28)
    def test_pinned_f104_baseline(self):
        path=Path(os.environ["F104_ARTIFACT_ZIP"])
        previous=F.read_f104(path)
        self.assertEqual(len(previous["new_native_C_stars"]),7)
        self.assertEqual(previous["new_native_C_call_count"],71)
    def test_f105_failure_artifact_is_pinned(self):
        prior=F.read_f105_failed(Path(os.environ["F105_ARTIFACT_ZIP"]))
        self.assertEqual(prior["status"],"FAIL_CLOSED")
        self.assertEqual(len(prior["new_native_C_stars"]),6)
    def test_native_route_and_scope(self):
        source=(ROOT/"f106_sixth_mesh_peak_probe.py").read_text()
        self.assertIn('"-r"',source)
        self.assertNotIn('"-s"',source)
        self.assertIn("do not prove a continuum turning point",source.lower())

if __name__=="__main__":unittest.main()
