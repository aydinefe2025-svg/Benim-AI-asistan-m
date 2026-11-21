import unittest
from rns_absoluteH_fixed_mass import solve_near_center, NumericalRootError, TARGET

class CorrectedMassRootTests(unittest.TestCase):
    def star(self,rho):
        return {"mass_msun":TARGET + 2e-15*(rho-1e15),
                "radius_eq_km":12.5,"central_energy_density_g_cm3":rho}
    def test_model_already_on_target(self):
        m,record=solve_near_center(self.star,1e15)
        self.assertAlmostEqual(m["mass_msun"],TARGET)
        self.assertEqual(record["root_trace"],[])
    def test_root_from_over_target(self):
        m,record=solve_near_center(self.star,1.02e15)
        self.assertLess(abs(m["mass_msun"]-TARGET),0.0015)
        self.assertIn("bracket_g_cm3",record)
    def test_root_from_under_target(self):
        m,record=solve_near_center(self.star,.98e15)
        self.assertLess(abs(m["mass_msun"]-TARGET),0.0015)
        self.assertIn("bracket_g_cm3",record)
    def test_never_use_nonfinite_root(self):
        def bad(rho):raise RuntimeError("NaN RNS star")
        with self.assertRaises(NumericalRootError):
            solve_near_center(bad,1e15)
    def test_prevent_nonphysical_extrapolation(self):
        with self.assertRaises(ValueError):
            solve_near_center(self.star,-1.0)

if __name__=="__main__":unittest.main()
