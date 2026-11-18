"""F53 mocked numerical tests. They do not establish physical EOS stability."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import f53_wff1_constant_j as f53

TARGET_J=2.345e48

def fake_direct_star(ec,ratio):
    ec15=ec/1e15
    return {"ec_g_cm3":ec,"axis_ratio":ratio,
            "J_cgs":TARGET_J*(1 + 80*(.990-ratio)),
            "mass_msun":2.123 - .04*(ec15-2.8)**2,
            "radius_eq_km":9.6,
            "spin_hz":340 + (1-ratio)*500,
            "rns_M0_msun_NOT_PHYSICAL":2.5}

class F53Tests(unittest.TestCase):
    def test_exact_J_brent_from_direct_solver(self):
        result,trace=f53.solve_at_J(fake_direct_star,2.80e15,TARGET_J,.991)
        self.assertAlmostEqual(result["axis_ratio"],.990,places=7)
        self.assertLess(abs(result["relative_J_residual"]),f53.RNS_TARGET_J_REL_TOL)
        self.assertGreater(len(trace),2)
        self.assertAlmostEqual(result["mass_msun"],fake_direct_star(2.80e15,.990)["mass_msun"])

    def test_missing_J_bracket_never_infers_root(self):
        def wrongJ(ec,ratio):
            x=fake_direct_star(ec,ratio)
            x["J_cgs"]=2*TARGET_J
            return x
        with self.assertRaisesRegex(ValueError,"NO_DIRECT_C_CONSTANT_J_BRACKET"):
            f53.solve_at_J(wrongJ,2.8e15,TARGET_J,.990)

    def test_reject_nonfinite_J(self):
        def nanJ(ec,ratio):
            x=fake_direct_star(ec,ratio)
            x["J_cgs"]=float("nan")
            return x
        with self.assertRaisesRegex(ValueError,"NO_DIRECT_C_CONSTANT_J_BRACKET"):
            f53.solve_at_J(nanJ,2.8e15,TARGET_J,.99)

    def test_constant_J_turnover_is_not_dynamical_proof(self):
        seq=[]
        for x in [2.50,2.60,2.70,2.75,2.80,2.85,2.9,3.0,3.1]:
            seq.append({**fake_direct_star(x*1e15,.990),"status":"DIRECT_C_FIXED_J_PASS"})
        result=f53.turnover(seq)
        self.assertEqual(result["status"],"SAMPLED_CONSTANT_J_MASS_TURNOVER_BRACKETED")
        self.assertEqual(result["dynamical_stability"],"NOT_TESTED")
        self.assertEqual(result["physical_nuclear_EOS_validity"],"NOT_ESTABLISHED")
        self.assertAlmostEqual(result["sampled_peak_M_msun"],2.123)

    def test_monotone_sequence_no_physical_max(self):
        seq=[{**fake_direct_star(x*1e15,.99),"status":"DIRECT_C_FIXED_J_PASS"}
             for x in [2.0,2.1,2.2,2.3,2.4,2.5,2.6,2.7]]
        self.assertEqual(f53.turnover(seq)["status"],"UNBRACKETED_CONSTANT_J_MASS_MAXIMUM")

    def test_insufficient_good_models_remain_unverified(self):
        seq=[{**fake_direct_star(x*1e15,.99),"status":"DIRECT_C_FIXED_J_PASS"} for x in (2.6,2.7)]
        self.assertEqual(f53.turnover(seq)["status"],"INSUFFICIENT_DIRECT_C_STARS")

if __name__=="__main__":
    unittest.main()
