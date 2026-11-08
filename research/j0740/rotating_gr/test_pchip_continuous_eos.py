"""Independent analytic polynomial extrema and source-identity audit tests."""
import unittest
import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator
from pchip_continuous_eos import audit_arrays, extrema_on_interval

class ContinuousCandidateTests(unittest.TestCase):
    def test_power_law_exact_full_interval_derivative_and_sound_speed(self):
        x=np.linspace(-1.,2.,12); y=np.log(3.0)+2*x
        interp=PchipInterpolator(x,y)
        for i in range(len(x)-1):
            v=extrema_on_interval(interp.c[:,i],x[i+1]-x[i],x[i])
            self.assertAlmostEqual(v['derivative_min'],2.,places=10)
            self.assertAlmostEqual(v['derivative_max'],2.,places=10)
            self.assertAlmostEqual(v['cs2_max'],np.exp(-np.log(3.)-x[i])/2.,places=10)
            self.assertTrue(v['is_strictly_stable'])

    def test_natural_spline_overshoot_but_pchip_positive_everywhere(self):
        x=np.linspace(0,3,4); y=np.array([0.0,1.0,1.00001,2.0])
        naive=CubicSpline(x,y,bc_type='natural')
        self.assertLess(float(np.min(naive(np.linspace(0.,3.,1001),1))),0.)
        patch=PchipInterpolator(x,y)
        for i in range(3):
            v=extrema_on_interval(patch.c[:,i],x[i+1]-x[i],x[i])
            self.assertGreater(v['derivative_min'],0.)

    def test_full_polynomial_cs2_max_not_only_sampled_knots(self):
        x=np.linspace(0,3,7); y=np.array([0.,.3,.7,.75,1.,1.3,1.8])
        pp=PchipInterpolator(x,y)
        for i in range(len(x)-1):
            v=extrema_on_interval(pp.c[:,i],x[i+1]-x[i],x[i])
            dense=np.linspace(x[i],x[i+1],2000)
            q=np.exp(dense-pp(dense))/pp.derivative()(dense)
            self.assertGreaterEqual(v['cs2_max']+1e-8,float(q.max()))
            self.assertLessEqual(v['cs2_min']-1e-8,float(q.min()))

    def test_monotone_arrays_preserved_and_source_negative_flagged(self):
        p=np.geomspace(.1,10.,55)
        e=3.*p**1.5
        cs2=p/(1.5*e)
        cs2[10]=-0.1  # original LAL has different native derivative
        a=audit_arrays(p,e,cs2)
        self.assertEqual(a['source_negative_cs2_knot_count'],1)
        self.assertTrue(a['pchip_exact_interval_derivative_positive'])
        self.assertGreater(a['pchip_continuous_dloge_dlogp_min'],0.)
        self.assertTrue(a['pchip_entire_table_causality_screen'])

    def test_original_nonmonotone_energy_rejected_not_sorted(self):
        p=np.geomspace(.1,10.,35);e=p**1.3;e[12]=e[11]*.9
        with self.assertRaisesRegex(ValueError,'not strictly monotonic'):
            audit_arrays(p,e,np.ones_like(p))

    def test_overfast_eos_remains_flagged_without_clipping(self):
        p=np.geomspace(.1,10.,55);e=.12*p**.4
        cs2=p/(.4*e)
        a=audit_arrays(p,e,cs2)
        self.assertFalse(a['pchip_entire_table_causality_screen'])
        self.assertGreater(a['pchip_continuous_cs2_max'],1.)

    def test_flat_derivative_is_not_a_pass(self):
        v=extrema_on_interval(np.array([0.,0.,0.,1.]),1.,0.)
        self.assertFalse(v['is_strictly_stable'])
        self.assertIsNone(v['cs2_max'])

if __name__=='__main__':unittest.main()
