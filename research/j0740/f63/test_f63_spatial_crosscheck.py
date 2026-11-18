"""Local controls for independent 201x401 C RNS comparison. Fake stars not data."""
from __future__ import annotations
import unittest,sys,types
try:import jester_to_rns
except ImportError:
    m=types.ModuleType('jester_to_rns')
    m.from_jester_npz=lambda *a,**k:None
    m.write_rns=lambda *a,**k:None
    sys.modules['jester_to_rns']=m
from f63_spatial_constant_j_crosscheck import pair_gate,fine_turning,NEAR_PEAK_E15

def fake(ec,m,r):
    return {'ec_g_cm3':ec,'mass_msun':m,'radius_eq_km':r,'J_cgs':6e48,'relative_J_residual':1e-8}
class TestF63Spatial(unittest.TestCase):
    def test_two_source_C_grid_values(self):
        x=pair_gate(fake(2e15,2.48,11.35),fake(2e15,2.4801,11.36))
        self.assertTrue(x['mesh_acceptance'])
        self.assertAlmostEqual(x['fine_minus_coarse_radius_km'],.01)
    def test_reject_wrong_center(self):
        with self.assertRaisesRegex(ValueError,'SOURCE_OR_C_MODEL_INVALID'):
            pair_gate(fake(2e15,2.48,11.35),fake(2.2e15,2.48,11.35))
    def test_reject_spatial_radius_error(self):
        self.assertFalse(pair_gate(fake(2e15,2.48,11.35),fake(2e15,2.48,11.55))['mesh_acceptance'])
    def test_reject_angular_momentum_error(self):
        bad=fake(2e15,2.48,11.35);bad['relative_J_residual']=1e-2
        self.assertFalse(pair_gate(fake(2e15,2.48,11.35),bad)['mesh_acceptance'])
    def test_fine_peak_mathematically_bracketed(self):
        rows=[{'ec_e15':2.04+i*.01,'fine':{'mass_msun':2.475-.004*(i-3)**2}} for i in range(7)]
        self.assertEqual(fine_turning(rows)['status'],'FINE_201x401_SAMPLED_FIXED_J_PEAK_BRACKETED')
    def test_monotone_fine_not_certified(self):
        rows=[{'ec_e15':2.04+i*.01,'fine':{'mass_msun':2.475+i*.001}} for i in range(7)]
        self.assertEqual(fine_turning(rows)['status'],'FINE_MESH_TURNING_NOT_RESOLVED')
    def test_expected_fine_7_source_densities(self):
        self.assertEqual(len(NEAR_PEAK_E15),7)

if __name__=='__main__':unittest.main()