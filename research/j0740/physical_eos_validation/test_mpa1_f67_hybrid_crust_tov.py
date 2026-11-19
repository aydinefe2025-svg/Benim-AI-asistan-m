import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mpa1_jester_hybrid_crust_tov import DEFAULT_TABLE, EOS, run


class HybridMPA1CrustTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eos = EOS(DEFAULT_TABLE, subdivisions=1, quadrature=24)
        cls.result = run(DEFAULT_TABLE)

    def test_pinned_model_and_separate_status(self):
        r = self.result
        self.assertEqual(r["provenance"]["F67_table_sha256"],
                         "d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22")
        self.assertTrue(r["provenance"]["original_data_modified"] is False)
        self.assertEqual(r["limits"]["physical_EOS_acceptance"], "NOT_ESTABLISHED")
        self.assertEqual(r["limits"]["new_hybrid_model_RNS"], "NOT_RUN")
        self.assertEqual(r["limits"]["final_EOS_Bayes"], "NOT_RUN")

    def test_crust_has_vacuum_surface_first_law_and_absolute_mu_anchor(self):
        p0, e0 = self.eos.crust_state_h(0.0)
        self.assertEqual(p0, 0.0)
        self.assertEqual(e0, 0.0)
        self.assertAlmostEqual(self.eos.h0, 1.4540409895687953e-14, delta=2e-26)
        prior_n = self.eos.n0
        self.assertGreater(prior_n, 0.0)
        rel = self.result["crust_join"]["n_first_law_over_n0_max_relative_residual"]
        self.assertLess(rel, 1e-12)
        self.assertLess(self.result["crust_join"]["native_enthalpy_relative_max_abs_difference"], 1e-7)

    def test_continuous_interpolant_is_stable_and_causal(self):
        c = self.result["causality"]
        self.assertEqual(c["core_intervals_checked"], 2424)
        self.assertTrue(c["whole_defined_model_causal"])
        self.assertGreater(c["core_cs2_min"], 0.0)
        self.assertLessEqual(c["core_cs2_max"], 1.0)
        self.assertLessEqual(c["crust_cs2_join"], 1.0)
        self.assertEqual(c["tail_cs2"], 1.0)

    def test_turning_point_converges_and_independent_tov_agrees(self):
        t = self.result["tov"]
        self.assertAlmostEqual(t["fine_subdiv2_quad48_Mmax"]["M_msun"],
                               2.4619767496707743, delta=2e-5)
        self.assertLess(abs(t["fine_minus_coarse_mass_msun"]), 2e-5)
        self.assertLess(abs(t["fine_minus_coarse_radius_km"]), 0.01)
        self.assertLess(t["relative_difference_independent_mass"], 5e-5)
        self.assertLess(t["relative_difference_independent_radius"], 5e-5)
        self.assertEqual(t["fine_subdiv2_quad48_Mmax"]["surface_pressure_geom"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
