"""End-to-end tests for the named BPS–MPA1 hybrid TOV candidate."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import jester_bps_mpa1_matched_tov as model

class MatchedEOSValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=model.run()

    def test_pinned_sources_and_separate_model_identity(self):
        self.assertEqual(self.r["model"],"JESTER_BPS_CRUST_LAL_MPA1_HIGH_PRESSURE_CROSSING_CAUSAL_TAIL_V1")
        self.assertEqual(self.r["source"]["original_jester_mpa1_npz_sha256"],"0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22")
        self.assertFalse(self.r["source"]["original_sources_modified"])

    def test_pressure_energy_and_firstlaw_density_join(self):
        q=self.r["transition"]
        self.assertGreaterEqual(q["crossing_count_in_stable_overlap"],1)
        self.assertLess(abs(q["energy_continuity_relative_residual"]),2e-10)
        self.assertLess(abs(q["firstlaw_vs_BPS_n_relative_residual"]),5e-5)
        self.assertLess(q["cs2_jump_absolute"],0.01)

    def test_continuous_piecewise_causality_and_stability(self):
        q=self.r["continuous_causality_and_stability"]
        self.assertTrue(q["all_piecewise_segments_causal"])
        for seg in q["segments"]:
            self.assertGreaterEqual(seg["cs2_min"],0)
            self.assertLessEqual(seg["cs2_max"],1)

    def test_independent_tov_formulations_and_convergence(self):
        q=self.r["TOV"]
        self.assertLess(q["uv_relative_mass_difference"],5e-5)
        self.assertLess(q["uv_relative_radius_difference"],5e-5)
        coarse=q["coarse_scan_52_rtol_2e-8_turning_point"]
        fine=q["fine_scan_84_rtol_2e-10_turning_point"]
        self.assertLess(abs(fine["M_msun"]-coarse["M_msun"]),2e-5)
        self.assertLess(abs(fine["R_km"]-coarse["R_km"]),0.01)
        self.assertAlmostEqual(q["M1p4"]["M_msun"],1.4,places=6)
        self.assertAlmostEqual(q["M2p073"]["M_msun"],2.073,places=6)

    def test_unrun_inference_and_rotation_are_not_claimed(self):
        q=self.r["limits"]
        self.assertEqual(q["new_model_RNS"],"NOT_RUN")
        self.assertEqual(q["source_native_XPSI_marginalization"],"NOT_RUN")
        self.assertEqual(q["final_EOS_Bayes"],"NOT_RUN")

if __name__=="__main__": unittest.main(verbosity=2)

