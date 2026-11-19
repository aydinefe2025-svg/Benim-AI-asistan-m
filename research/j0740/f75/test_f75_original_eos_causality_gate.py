import unittest
import numpy as np
from f75_original_eos_causality_gate import inspect_sample_arrays,source_central_bracket

class CausalityUnitTests(unittest.TestCase):
    def setUp(self):
        self.p=np.linspace(1e-13,1e-11,20)
        self.e=np.linspace(1e-11,1e-9,20)
        self.cs=np.linspace(.01,.9,20)
        self.centre=2.0e15
    def test_pass_source_knots_not_global_physics(self):
        r=inspect_sample_arrays(self.p,self.e,self.cs,self.centre)
        self.assertEqual(r['reference_star_source_sampled_causality_gate'],'PASS_KNOTS_ONLY')
    def test_superluminal_core_rejected(self):
        c=self.cs.copy();c[5]=1.001
        r=inspect_sample_arrays(self.p,self.e,c,self.centre)
        self.assertEqual(r['superluminal_cs2_knots_inside_reference_star_EOS_range'],1)
        self.assertEqual(r['reference_star_source_sampled_causality_gate'],'FAIL_OR_UNRESOLVED')
    def test_outside_core_is_not_inside_core(self):
        c=self.cs.copy();c[-1]=1.2
        r=inspect_sample_arrays(self.p,self.e,c,1.0e14)
        self.assertEqual(r['superluminal_cs2_knots_inside_reference_star_EOS_range'],0)
        self.assertEqual(r['source_superluminal_cs2_knots'],1)
    def test_negative_outer_crust_rejected(self):
        c=self.cs.copy();c[1]=-.2
        self.assertEqual(inspect_sample_arrays(self.p,self.e,c,self.centre)['reference_star_source_sampled_causality_gate'],'FAIL_OR_UNRESOLVED')
    def test_negative_energy_step_detected(self):
        e=self.e.copy();e[2]=e[1]-1e-12
        r=inspect_sample_arrays(self.p,e,self.cs,self.centre)
        self.assertEqual(r['source_energy_nonincreasing_edges'],1)
        self.assertEqual(r['reference_star_source_sampled_causality_gate'],'FAIL_OR_UNRESOLVED')
    def test_bad_pressure_rejected(self):
        p=self.p.copy();p[3]=p[2]
        with self.assertRaises(ValueError):inspect_sample_arrays(p,self.e,self.cs,self.centre)
    def test_nan_rejected(self):
        c=self.cs.copy();c[3]=float('nan')
        with self.assertRaises(ValueError):inspect_sample_arrays(self.p,self.e,c,self.centre)
    def test_reference_mass_bracket(self):
        stars=[{'mass_msun':m,'central_energy_density_g_cm3':e} for m,e in [(1.9,1e15),(2.1,2e15),(2.0,3e15)]]
        ec,br=source_central_bracket(stars,2.0)
        self.assertAlmostEqual(ec,1.5e15)
    def test_missing_target_bracket_rejected(self):
        s=[{'mass_msun':m,'central_energy_density_g_cm3':e} for m,e in [(0.5,1e15),(.9,2e15),(0.8,3e15)]]
        with self.assertRaises(ValueError):source_central_bracket(s,2.073)
    def test_nonincreasing_mass_does_not_fabricate_reference(self):
        s=[{'mass_msun':m,'central_energy_density_g_cm3':e} for m,e in [(1.9,1e15),(1.8,2e15),(2.1,3e15)]]
        ec,_=source_central_bracket(s,2.0)
        self.assertGreater(ec,2e15)
if __name__=='__main__':unittest.main()