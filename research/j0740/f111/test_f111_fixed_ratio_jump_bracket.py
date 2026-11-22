#!/usr/bin/env python3
import os
import unittest
from pathlib import Path

from research.j0740.f111 import f111_fixed_ratio_jump_bracket as f111
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

class F111Preflight(unittest.TestCase):
    def test_immutable_physics_and_finer_density_plan(self):
        self.assertEqual(f111.GRID, "501x1001")
        self.assertEqual(f111.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(f111.INTERIOR_RHO_TICKS_1E10, tuple(range(262221, 262230)))
        self.assertEqual(len(f111.INTERIOR_RHO_TICKS_1E10), 9)
        self.assertEqual(f106.TARGET_J, 4.8245626795750385e48)
        self.assertEqual(f106.J_REL_TOL, 3e-5)

    def test_f110_checksum_raw_journal_and_endpoint_reuse(self):
        result, rows = f111.read_f110(Path(os.environ["F110_ARTIFACT_ZIP"]))
        self.assertEqual(result["status"], "F110_FIXED_RATIO_DENSITY_SCAN_COMPLETE")
        self.assertEqual(len(rows), 18)
        for label in ("A", "B"):
            points = result["series_by_fixed_ratio"][label]["points"]
            ticks = {int(round(p["rho_g_cm3"] / 1e10)) for p in points}
            self.assertIn(262220, ticks)
            self.assertIn(262230, ticks)
            self.assertEqual(len(points), 11)

    def test_only_interior_points_are_new(self):
        ticks = set(f111.INTERIOR_RHO_TICKS_1E10)
        self.assertEqual(len(ticks), 9)
        self.assertFalse({262220, 262230} & ticks)
        self.assertEqual(2 * len(ticks), 18)

    def test_claim_limit_and_no_overwrite_guard(self):
        source = Path(f111.__file__).read_text()
        self.assertIn("NEVER_OVERWRITE_F111_RAW_DENSITY_JOURNAL", source)
        self.assertIn('"diagnostic_only": True', source)
        self.assertIn("not fixed-J solutions", source)
        self.assertIn("cannot establish", source)

if __name__ == "__main__":
    unittest.main()
