import unittest

from mpa1_pchip_partial_f38_evidence import (
    F68_RUN_ID, M_ANCHOR, M_SIG, M_MU, q_radio, run,
)
import numpy as np


class PartialF38EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run()

    def test_source_and_model_labels_fail_closed(self):
        r = self.result
        self.assertEqual(F68_RUN_ID, 44490729799)
        self.assertEqual(r["status"], "PASS_PARTIAL_APPROXIMATE_EVIDENCE_CONTRIBUTION_ONLY")
        self.assertEqual(r["model"], "MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL")
        self.assertEqual(r["limits"]["complete_EOS_evidence"], "NOT_ESTABLISHED")
        self.assertEqual(r["limits"]["seven_original_EOS_model_Bayes"], "NOT_RUN")
        self.assertEqual(r["limits"]["source_native_XPSI_photon_reanalysis"], "NOT_RUN")

    def test_radio_mass_density_normalizes(self):
        m = np.linspace(M_MU - 5*M_SIG, M_MU + 5*M_SIG, 100001)
        self.assertAlmostEqual(float(np.trapezoid(q_radio(m), m)), 1.0, places=8)
        self.assertAlmostEqual(self.result["mass_prior"]["prior_mass_fraction_in_integrated_interval"],
                               0.5425050954449053, places=12)

    def test_only_direct_anchor_interval_is_integrated(self):
        self.assertEqual(self.result["integration"]["mass_interval_msun"],
                         [float(M_ANCHOR[0]), float(M_ANCHOR[-1])])
        self.assertIn("NOT_INTEGRATED", self.result["integration"]["outside_interval"])
        self.assertEqual(len(self.result["integration"]["values"]), 6)

    def test_weighted_and_resampled_partial_integrals_reproduce(self):
        expected = {
            "weighted_0.015_0.20": 1.3273989502876042,
            "weighted_0.025_0.35": 1.2593660379083071,
            "weighted_0.040_0.50": 1.1635652701181920,
            "resampled_0.015_0.20": 1.3302139181129240,
            "resampled_0.025_0.35": 1.2607226612472350,
            "resampled_0.040_0.50": 1.1643502063384963,
        }
        for name, value in expected.items():
            rec = self.result["integration"]["values"][name]
            self.assertAlmostEqual(rec["partial_integral"], value, delta=2e-10)
            self.assertLess(rec["grid_delta_20001_to_40001"], 2e-9)


if __name__ == "__main__":
    unittest.main(verbosity=2)

