import unittest
import numpy as np
from rns_crust_knot_transfer import (analyze_transfer, C2_CGS, RHO_CONVERSION_CGS,
                                   PRESSURE_CONVERSION_CGS, rns_p_at_e_cubic_cs2,
                                   profile_c_interpolant)


def make_source(negative=True):
    p_cgs = np.geomspace(1e30,1e36,150)
    rho = np.geomspace(3e9,3e15,150)
    e = rho / RHO_CONVERSION_CGS
    native = np.full(150, 0.4)
    if negative:
        e[25] = e[24] * 0.99
        native[25] = -0.17
    return e,p_cgs/PRESSURE_CONVERSION_CGS,native


def make_rows():
    rho = np.geomspace(3e9,3e15,196)
    p=0.4 * C2_CGS * rho
    h=np.linspace(1,2,len(rho))
    n=np.linspace(1e30,2e30,len(rho))
    return np.column_stack([rho,p,h,n])


class CrustTransferTests(unittest.TestCase):
    def test_negative_source_node_and_positive_rns_secant_are_both_reported(self):
        e,p,cs=make_source()
        out=analyze_transfer(e,p,cs,make_rows(),1.5e15)
        self.assertEqual(out['native_negative_cs2_nodes'],1)
        self.assertEqual(out['rns_input_nonpositive_secant_count'],0)
        self.assertTrue(out['native_source_negative_knot_present_but_rns_secants_positive'])
        self.assertLess(out['native_negative_node_mapping'][0]['native_analytic_cs2_over_c2'],0)
        self.assertTrue(out['native_negative_node_mapping'][0]['below_rotating_center'])

    def test_no_negative_native_node_does_not_create_false_warning(self):
        e,p,cs=make_source(False)
        out=analyze_transfer(e,p,cs,make_rows(),1.5e15)
        self.assertFalse(out['native_source_negative_knot_present_but_rns_secants_positive'])
        self.assertEqual(out['native_negative_cs2_nodes'],0)

    def test_supraluminal_segment_below_center_is_reported(self):
        e,p,cs=make_source(False)
        r=make_rows()
        r[130:,1]=r[129,1]+2*C2_CGS*(r[130:,0]-r[129,0])
        out=analyze_transfer(e,p,cs,r,1.8e15)
        self.assertGreater(out['rns_input_supraluminal_secants_wholly_below_center'],0)

    def test_c_four_point_cubic_exact_linear_eos(self):
        rows=make_rows()
        for rho in (rows[2,0], rows[13,0]*1.11, 1.5e15):
            diag=rns_p_at_e_cubic_cs2(rows,rho)
            self.assertAlmostEqual(diag["cs2_over_c2"],.4,places=10)
            self.assertAlmostEqual(diag["dlogp_dlogrho"],1.,places=10)

    def test_cubic_profile_for_causal_linear_eos(self):
        diag=profile_c_interpolant(make_rows(),1.5e15,per_interval=4)
        self.assertEqual(diag["negative_sample_count"],0)
        self.assertIsNone(diag["negative_cs2_rho_range_g_cm3"])
        self.assertGreaterEqual(diag["min_cs2_rho_g_cm3"],3e9)
        self.assertLessEqual(diag["min_cs2_rho_g_cm3"],1.5e15)
        self.assertEqual(diag["superluminal_sample_count"],0)
        self.assertAlmostEqual(diag["max_cs2_over_c2"],.4,places=10)

    def test_cubic_rejects_outside_table(self):
        with self.assertRaisesRegex(ValueError,"Invalid"):
            rns_p_at_e_cubic_cs2(make_rows(),1e17)

    def test_center_outside_table_refused(self):
        e,p,cs=make_source(False)
        with self.assertRaisesRegex(ValueError,'Invalid'):
            analyze_transfer(e,p,cs,make_rows(),1e18)

    def test_nonmonotone_rns_density_refused(self):
        e,p,cs=make_source(False)
        r=make_rows();r[10,0]=r[9,0]
        with self.assertRaisesRegex(ValueError,'Invalid'):
            analyze_transfer(e,p,cs,r,1.5e15)

    def test_nonmonotone_source_pressure_refused(self):
        e,p,cs=make_source(False);p[10]=p[9]
        with self.assertRaisesRegex(ValueError,'Invalid'):
            analyze_transfer(e,p,cs,make_rows(),1.5e15)

    def test_zero_native_cs2_is_not_named_negative(self):
        e,p,cs=make_source(False);cs[20]=0
        out=analyze_transfer(e,p,cs,make_rows(),1.5e15)
        self.assertEqual(out['native_negative_cs2_nodes'],0)

    def test_native_source_out_of_rns_support_is_not_silently_ignored(self):
        e,p,cs=make_source(False)
        p[25]=1e40/PRESSURE_CONVERSION_CGS
        cs[25]=-.1
        # Source remains monotone? Not so: malformed source must be refused.
        with self.assertRaisesRegex(ValueError,'Invalid'):
            analyze_transfer(e,p,cs,make_rows(),1.5e15)


if __name__ == '__main__':
    unittest.main()
