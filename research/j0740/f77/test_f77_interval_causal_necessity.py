import unittest
import numpy as np
from f77_interval_causal_necessity import audit_source_segments, classify_star_segments

class F77CausalTheoremTest(unittest.TestCase):
    def setUp(self):
        self.p=np.arange(1,21,dtype=float)*1e-9
        self.e=np.arange(1,21,dtype=float)*2.0e-9
    def audit(self,p=None,e=None):
        return audit_source_segments(self.p if p is None else p,self.e if e is None else e)
    def core(self,segments):
        return float(np.max(segments['upper_densities']))
    def test_causal_normal_secant(self):
        s=self.audit(); self.assertFalse(np.any(s['bad_energy'])); self.assertFalse(np.any(s['bad_super']))
    def test_superluminal_average_detected_without_local_derivative(self):
        e=self.e.copy();e[4]=e[3]+.25e-9
        s=self.audit(e=e);self.assertTrue(s['bad_super'][3])
        self.assertEqual(classify_star_segments(s,self.core(s))['status'],'REFUTED_BY_SOURCE_SEGMENT')
    def test_negative_energy_difference_detected(self):
        e=self.e.copy();e[4]=e[3]-.2e-9
        s=self.audit(e=e);self.assertTrue(s['bad_energy'][3])
        self.assertEqual(classify_star_segments(s,self.core(s))['status'],'REFUTED_BY_SOURCE_SEGMENT')
    def test_equal_delta_e_delta_p_is_not_refuted(self):
        e=self.p.copy();s=self.audit(e=e)
        self.assertFalse(np.any(s['bad_super']));self.assertFalse(np.any(s['bad_energy']))
    def test_just_inside_margin_not_falsely_refuted(self):
        e=self.p*(1-1e-12)
        self.assertFalse(np.any(self.audit(e=e)['bad_super']))
    def test_strongly_above_c_speed_is_refuted(self):
        e=self.p*.9
        self.assertTrue(np.all(self.audit(e=e)['bad_super']))
    def test_boundary_cut_segment_is_excluded(self):
        e=self.e.copy();e[-1]=e[-2]+.1e-9
        s=self.audit(e=e)
        core=float((e[-1]+e[-2])/2*299792458**2/6.67430e-11/1000)
        q=classify_star_segments(s,core)
        self.assertEqual(q['status'],'NECESSARY_CONDITION_ONLY_UNCERTIFIED')
    def test_whole_source_range_counted(self):
        s=self.audit();q=classify_star_segments(s,self.core(s))
        self.assertEqual(q['fully_inside_segments'],len(self.p)-1)
    def test_invalid_pressure_rejected(self):
        p=self.p.copy();p[5]=p[4]
        with self.assertRaises(ValueError):self.audit(p=p)
    def test_nonfinite_source_rejected(self):
        e=self.e.copy();e[5]=np.nan
        with self.assertRaises(ValueError):self.audit(e=e)
    def test_wrong_core_rejected(self):
        s=self.audit()
        with self.assertRaises(ValueError):classify_star_segments(s,0)
    def test_outside_support_unresolved(self):
        s=self.audit();q=classify_star_segments(s,self.core(s)*2)
        self.assertEqual(q['status'],'UNRESOLVED_SOURCE_COVERAGE')
    def test_scaling_pressure_energy_invariant(self):
        a=self.audit();b=self.audit(self.p*3,self.e*3)
        np.testing.assert_array_equal(a['bad_super'],b['bad_super'])
        np.testing.assert_array_equal(a['bad_energy'],b['bad_energy'])
    def test_numerical_margin_invalid_rejected(self):
        with self.assertRaises(ValueError):audit_source_segments(self.p,self.e,rel_margin=.01)
    def test_pass_is_necessary_not_certified(self):
        s=self.audit();q=classify_star_segments(s,self.core(s))
        self.assertIn('UNCERTIFIED',q['status'])

if __name__=='__main__':unittest.main()