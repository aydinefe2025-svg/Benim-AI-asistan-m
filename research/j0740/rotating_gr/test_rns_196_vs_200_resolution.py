import unittest
from rns_196_vs_200_resolution import compare_model,audit

def model(m=2.073,r=12.53,rho=1.0e15,spin=346.5):
    return {"mass_msun":m,"radius_eq_km":r,
            "central_energy_density_g_cm3":rho,"spin_hz_reported":spin}

class ResolutionStressTests(unittest.TestCase):
    def test_close_both_values_pass(self):
        x=compare_model(model(),model(2.074,12.54))
        self.assertTrue(x["screen_pass"])
        self.assertAlmostEqual(x["delta_radius_eq_km"],.01,places=6)
    def test_radius_mismatch_flagged(self):
        x=compare_model(model(),model(2.074,12.88))
        self.assertFalse(x["screen_pass"])
    def test_mass_mismatch_flagged(self):
        x=compare_model(model(),model(2.15,12.54))
        self.assertFalse(x["screen_pass"])
    def test_central_density_drift_rejected(self):
        with self.assertRaisesRegex(ValueError,"densities"):
            compare_model(model(),model(rho=1.1e15))
    def test_missing_output_rejected(self):
        with self.assertRaisesRegex(ValueError,"Incomplete"):
            compare_model({"mass_msun":2},model())
    def test_partial_prior_run_rejected(self):
        with self.assertRaisesRegex(ValueError,"identity"):
            audit({"status":"PARTIAL_NOT_FINAL"},None,None,None)

if __name__=="__main__":
    unittest.main()
