#!/usr/bin/env python3
import os
import unittest
from pathlib import Path
from research.j0740.f119 import f119_fine_intradensity_scan as f119

class F119Preflight(unittest.TestCase):
    def test_f118_baseline_and_five_fine_density_ticks(self):
        self.assertEqual(f119.GRID, "2501x5001")
        self.assertEqual(f119.RHO_TICKS_1E8, (26222855,26222860,26222865,26222870,26222875))
        result, rows, f116 = f119.read_f118(Path(os.environ["F118_ARTIFACT_ZIP"]))
        self.assertEqual(result["status"], "F118_INTRADENSITY_FIXEDJ_SCAN_COMPLETE")
        self.assertEqual(len(rows), 15)
        self.assertEqual(len(result["fixed_J_solutions"]), 3)
        self.assertEqual(f116["status"], "F116_FIFTH_GRID_FIXEDJ_ROOTS_COMPLETE")
        self.assertEqual([round(x["rho_g_cm3"]/1e10) for x in f116["fixed_J_solutions"]], [262228,262229])

    def test_source_pins_and_claim_limit(self):
        self.assertEqual(f119.EOS_SHA, "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331")
        self.assertEqual(f119.RNS_COMMIT, "97e85d325a33e37f702306414533f6cd77812477")
        source = Path(f119.__file__).read_text()
        self.assertIn('"diagnostic_only": True', source)
        self.assertIn("do not establish", source)
        self.assertIn("NEVER_OVERWRITE_F119_RAW_FIXEDJ_JOURNAL", source)

if __name__ == "__main__":
    unittest.main()
