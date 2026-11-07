import unittest
import numpy as np
from rns_three_path_consistency import interp_four_log,at_pressure,table_profile,C2_CGS,audit


def synthetic(n=196):
    rho=np.geomspace(1e10,1e16,n)
    p=0.4*C2_CGS*rho
    h=2*(p/p[0])**.25
    n0=1e20*(rho/rho[0])
    return np.column_stack([rho,p,h,n0])

class CThreePathTests(unittest.TestCase):
    def test_upstream_c_extrapolates_and_reports_support_violation(self):
        x=np.geomspace(1,1000,196)
        d=interp_four_log(x,x*2,0.998,allow_extrapolation=True)
        self.assertTrue(d["outside_tabulated_support"])
        self.assertGreater(d["extrapolation_log10_decades"],0)
        self.assertAlmostEqual(d["value"],1.996,places=7)

    def test_exact_polytropic_e_at_p(self):
        rows=synthetic()
        for p in (rows[3,1],rows[60,1]*1.06,rows[-8,1]):
            a=at_pressure(rows,p)
            self.assertAlmostEqual(a['e_at_p_effective_cs2_over_c2'],.4,places=9)
            self.assertAlmostEqual(a['p_at_e_roundtrip_relative_error_abs'],0,places=9)
            self.assertAlmostEqual(a['p_at_h_roundtrip_relative_error_abs'],0,places=9)
    def test_four_point_true_powerlaw(self):
        x=np.geomspace(1,1000,196)
        v=interp_four_log(x,x**1.5,12.345)
        self.assertAlmostEqual(v['value'],12.345**1.5,places=7)
        self.assertAlmostEqual(v['dlogy_dlogx'],1.5,places=10)
    def test_all_synthetic_stable(self):
        a=table_profile(synthetic(),1.05e15)
        self.assertEqual(a['e_at_p_negative_cs2_count'],0)
        self.assertEqual(a['e_at_p_superluminal_cs2_count'],0)
        self.assertEqual(a['h_at_p_negative_dlogh_dlogp_count'],0)
        self.assertLess(a['max_p_at_h_roundtrip_relative_error'],1e-8)
    def test_simulated_negative_e_at_p_slope_detected(self):
        r=synthetic()
        # Deliberately thin interval where e(p) decreases while p increases.
        r[22,0]=r[21,0]*0.95
        with self.assertRaisesRegex(ValueError,'Invalid'):
            table_profile(r,1e15)
    def test_no_outside_support(self):
        r=synthetic()
        with self.assertRaisesRegex(ValueError,'out-of-support'):
            interp_four_log(r[:,1],r[:,0],r[-1,1]*2)
    def test_nonmonotonic_h_rejected(self):
        r=synthetic()
        r[23,2]=r[22,2]
        with self.assertRaisesRegex(ValueError,'Invalid'):
            table_profile(r,1e15)
    def test_negative_and_zero_input_rejected(self):
        r=synthetic();r[2,1]=-1
        with self.assertRaises(ValueError):at_pressure(r,1e31)
    def test_partial_gr_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,'identity'):
            audit({'status':'NOT_FINAL'},None,None)
    def test_invalid_sample_density_rejected(self):
        with self.assertRaisesRegex(ValueError,'Invalid'):
            table_profile(synthetic(),1e15,samples_per_interval=99)
    def test_center_outside_rejected(self):
        with self.assertRaisesRegex(ValueError,'out-of-support'):
            table_profile(synthetic(),1e18)

if __name__=='__main__':unittest.main()
