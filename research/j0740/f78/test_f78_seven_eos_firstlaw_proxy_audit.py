import unittest
import numpy as np
from f78_seven_eos_firstlaw_proxy_audit import firstlaw_shape_ratio, bracket_center

class F78NativeFirstLawTests(unittest.TestCase):
    def setUp(self):
        self.p=np.linspace(1,100,101)*1e-8
        self.e=np.linspace(1,100,101)*1e-6
        self.h=np.linspace(.02,.08,101)
        self.n=self.e/1e-54
    def shape(self,**kwargs):
        q={k:getattr(self,k) for k in ('p','e','h','n')};q.update(kwargs)
        return firstlaw_shape_ratio(q['p'],q['e'],q['h'],q['n'])
    def test_exact_native_n_over_e(self):
        s=self.shape();self.assertLess(s['max_absolute_relative_n_over_e_residual'],1e-14)
    def test_firstlaw_at_reference_anchor(self):
        self.assertAlmostEqual(float(self.shape()['n_proxy_over_n_H'][0]),1.0,places=13)
    def test_analytical_enthalpy_formula_reproduced(self):
        s=self.shape();k=70
        expected=((self.e[k]+self.p[k])/(self.e[0]+self.p[0]))*np.exp(-(self.h[k]-self.h[0]))
        self.assertAlmostEqual(s['n_H_over_n0'][k],expected,places=12)
    def test_constant_H_shape_disagrees_if_nonzero_P_and_e_changes(self):
        h=np.linspace(.02,.02+1e-10,101)
        s=self.shape(h=h,p=self.p**.7)
        self.assertGreater(abs(float(s['n_proxy_over_n_H'][-1])-1),.001)
    def test_source_n_corruption_rejected(self):
        n=self.n.copy();n[35]*=1.00000001
        with self.assertRaisesRegex(ValueError,'energy_density_proxy'):self.shape(n=n)
    def test_pressure_duplicate_rejected(self):
        p=self.p.copy();p[20]=p[19]
        with self.assertRaises(ValueError):self.shape(p=p)
    def test_H_not_increasing_rejected(self):
        h=self.h.copy();h[20]=h[19]
        with self.assertRaises(ValueError):self.shape(h=h)
    def test_nonfinite_rejected(self):
        e=self.e.copy();e[10]=np.nan
        with self.assertRaises(ValueError):self.shape(e=e)
    def test_shape_mismatch_rejected(self):
        with self.assertRaises(ValueError):firstlaw_shape_ratio(self.p,self.e,self.h,self.n[:-1])
    def test_nonpositive_pressure_rejected(self):
        p=self.p.copy();p[0]=0.
        with self.assertRaises(ValueError):self.shape(p=p)
    def test_log_inverse_exact_at_knot(self):
        for k in (5,50,99):
            x=bracket_center(self.p,self.e,self.h,self.n,self.e[k])
            self.assertAlmostEqual(x['central_pressure_geom_m-2_DIAGNOSTIC'],float(self.p[k]),delta=self.p[k]*1e-13)
    def test_log_inverse_inside_bracket(self):
        e=np.geomspace(1e-6,100e-6,101);p=2*e;h=np.linspace(.02,1,101);n=e/1e-54
        target=np.sqrt(e[15]*e[16]);x=bracket_center(p,e,h,n,target)
        self.assertEqual(x['lower_source_knot'],15)
        self.assertAlmostEqual(x['log_e_interpolation_weight'],.5,places=11)
    def test_out_of_range_core_is_rejected(self):
        with self.assertRaises(ValueError):bracket_center(self.p,self.e,self.h,self.n,self.e.max()*2)
    def test_nonunique_core_bracket_is_rejected(self):
        e=self.e.copy();e[20]=e[19]*.8
        with self.assertRaisesRegex(ValueError,'not_exactly_one'):bracket_center(self.p,e,self.h,self.n,(e[18]+e[19])/2)
    def test_scaling_p_e_invariant(self):
        a=self.shape()['n_proxy_over_n_H']
        b=firstlaw_shape_ratio(self.p*9,self.e*9,self.h,self.n*9)['n_proxy_over_n_H']
        np.testing.assert_allclose(a,b,atol=1e-12,rtol=1e-14)
    def test_source_arrays_not_mutated(self):
        originals=[v.copy() for v in (self.p,self.e,self.h,self.n)]
        self.shape();bracket_center(self.p,self.e,self.h,self.n,self.e[40])
        for x,y in zip((self.p,self.e,self.h,self.n),originals):np.testing.assert_array_equal(x,y)
if __name__=='__main__':unittest.main()