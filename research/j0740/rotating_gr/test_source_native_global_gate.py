import unittest
import numpy as np
from source_native_global_gate import audit_arrays


class SourceNativeGateTests(unittest.TestCase):
    def setUp(self):
        self.p=np.geomspace(1.0, 4.0, 5)
        self.e=10.0+self.p
        self.n=self.e/2.0  # source's e/m_avg baryon approximation
        self.h=np.log(1+self.p/10)

    def test_monotone_causal_with_firstlaw_n_approx_detected(self):
        out=audit_arrays(self.p,self.e,self.n,self.h,np.full(5,.5),center_e=self.e[-1]-.001)
        self.assertEqual(out['negative_native_cs2_below_center'],0)
        self.assertEqual(out['negative_secants_below_center'],0)
        self.assertEqual(out['superluminal_secants_below_center'],0)
        self.assertGreater(out['firstlaw_n_normalized_terminal_fractional_mismatch'],0)

    def test_local_reverse_energy_fails_even_if_other_points_pass(self):
        e=self.e.copy();e[2]=e[1]-0.2
        out=audit_arrays(self.p,e,self.n,self.h,np.full(5,.5),center_e=self.e[-1]-.001)
        self.assertGreater(out['negative_secants_below_center'],0)
        self.assertEqual(out['sampled_source_screen'],'FAIL_IN_STAR')

    def test_source_native_n_may_retrace_when_energy_does(self):
        e=self.e.copy(); e[2]=e[1]-0.2
        out=audit_arrays(self.p,e,e/2,self.h,np.full(5,.5),center_e=self.e[-1]-.001)
        self.assertEqual(out['source_n_nonincreasing_edges_global'],1)
        self.assertEqual(out['sampled_source_screen'],'FAIL_IN_STAR')

    def test_superluminal_native_node_fails_even_when_secants_causal(self):
        cs=np.full(5,.5);cs[3]=1.08
        out=audit_arrays(self.p,self.e,self.n,self.h,cs,center_e=self.e[-1]-.001)
        self.assertEqual(out['superluminal_native_cs2_below_center'],1)
        self.assertEqual(out['sampled_source_screen'],'FAIL_IN_STAR')

    def test_source_nan_rejected(self):
        e=self.e.copy();e[0]=float('nan')
        with self.assertRaises(ValueError):audit_arrays(self.p,e,self.n,self.h,np.full(5,.5),center_e=self.e[-1]-.001)

    def test_pressure_not_increasing_rejected(self):
        p=self.p.copy();p[2]=p[1]
        with self.assertRaises(ValueError):audit_arrays(p,self.e,self.n,self.h,np.full(5,.5),center_e=self.e[-1]-.001)

    def test_source_analytic_negative_fails_even_monotone_discrete(self):
        cs=np.full(5,.5);cs[1]=-.17
        out=audit_arrays(self.p,self.e,self.n,self.h,cs,center_e=self.e[-1]-.001)
        self.assertEqual(out['negative_native_cs2_below_center'],1)
        self.assertEqual(out['sampled_source_screen'],'FAIL_IN_STAR')

if __name__=='__main__':unittest.main()
