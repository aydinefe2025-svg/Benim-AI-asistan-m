"""F56 synthetic tests: source-native audit, no fabricated original rotating stars."""
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f56_native_vs_modified_wff1 import compare_at_pressure,CAP
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'f42'))
from f42_causal_firstlaw_candidates import Candidate

def data(low_slope=.10):
    p=np.geomspace(1.,100.,120)
    e=5+low_slope*p
    cs2=np.full(len(p),1.5)
    return p,e,cs2,Candidate(p,e,cap=CAP,alpha=.6)

class F56NativeTests(unittest.TestCase):
    def test_original_remains_unchanged(self):
        p,e,cs,c=data()
        eorig=e.copy()
        center=c.e[80]
        result=compare_at_pressure(p,e,cs,c,center)
        self.assertTrue(np.array_equal(e,eorig))
        self.assertTrue(result['candidate_source_changed_nodes_global']>0)
        self.assertTrue(result['max_fractional_energy_lift_global']>0)
        self.assertEqual(result['native_cs2_superluminal_count_global'],len(p))
        self.assertTrue(result['F42_candidate_all_source_interval_cs2_positive_causal'])
        self.assertEqual(result['native_original_GR_stellar_mass_at_same_pressure'],'NOT_COMPUTED')
        self.assertAlmostEqual(result['F53_anchor_central_e15_g_cm3']*1e15,
                               center*299792458.0**2/6.67430e-11*1e-3)

    def test_native_at_equal_pressure_distinguished_from_modified(self):
        p,e,cs,c=data()
        result=compare_at_pressure(p,e,cs,c,c.e[65])
        self.assertLess(result['native_minus_modified_energy_fraction_at_equal_pressure'],0)
        self.assertAlmostEqual(result['native_cs2_over_c2_logp_interpolated_same_pressure'],1.5)

    def test_unmodified_causal_no_lift(self):
        p,e,cs,c=data(low_slope=2.)
        result=compare_at_pressure(p,e,cs,c,c.e[60])
        self.assertEqual(result['candidate_source_changed_nodes_global'],0)
        self.assertEqual(result['max_fractional_energy_lift_global'],0)

    def test_invalid_pressure_grid_fail_closed(self):
        p,e,cs,c=data()
        p[6]=p[5]
        with self.assertRaisesRegex(ValueError,'PRESSURE_GRID_INVALID'):
            compare_at_pressure(p,e,cs,c,c.e[80])

    def test_center_outside_source_fail_closed(self):
        p,e,cs,c=data()
        with self.assertRaisesRegex(ValueError,'CENTER_OUTSIDE'):
            compare_at_pressure(p,e,cs,c,c.e[-1]*10)

    def test_negative_native_cs2_reported_not_clipped(self):
        p,e,cs,c=data()
        cs[44]=-0.3
        result=compare_at_pressure(p,e,cs,c,c.e[85])
        self.assertEqual(result['native_cs2_negative_count_global'],1)
        self.assertEqual(result['native_cs2_min'],-0.3)

    def test_energy_decrease_detected_without_reordering(self):
        p,e,cs,c=data()
        e[22]=e[21]-0.001
        result=compare_at_pressure(p,e,cs,c,c.e[65])
        self.assertGreater(result['raw_native_energy_nonincreasing_interval_count'],0)

if __name__=='__main__':
    unittest.main()
