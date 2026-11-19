import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_jester_bps_mpa1_join as audit

class BPSJoinAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = audit.run()

    def test_source_hashes_and_rows(self):
        self.assertEqual(self.r["source"]["bps_original_npz_sha256"],
                         "372ce088e061997f7c05594e61e7c624a112d7ce66443c28c4633d03b7da6137")
        self.assertEqual(self.r["source"]["core_table_sha256"],
                         "d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22")
        self.assertEqual(self.r["source"]["bps_rows"], 130)

    def test_surface_chemical_potentials_close_but_eos_state_does_not(self):
        q = self.r["at_bps_upper_pressure"]
        self.assertLess(abs(q["relative_mu_mismatch"]), 5e-4)
        self.assertAlmostEqual(q["relative_energy_mismatch_core_over_bps"],
                               -0.04446460823524645, places=8)

    def test_equal_density_pressure_is_incompatible(self):
        q = self.r["at_equal_baryon_density"]
        self.assertAlmostEqual(q["relative_pressure_mismatch_core_over_bps"],
                               0.07593139553746786, places=8)

    def test_downstream_work_remains_open(self):
        self.assertEqual(self.r["new_bps_joined_tov"], "NOT_RUN")
        self.assertEqual(self.r["new_bps_joined_rns"], "NOT_RUN")
        self.assertEqual(self.r["final_eos_bayes"], "NOT_RUN")

if __name__ == "__main__":
    unittest.main()

