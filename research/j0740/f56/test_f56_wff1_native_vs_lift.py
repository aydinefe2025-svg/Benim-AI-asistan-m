"""F56 source-comparison unit tests. Synthetic EOS is not astrophysics."""
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f56_wff1_native_vs_lift import source_thermo,source_comparison
from f42_causal_firstlaw_candidates import Candidate

def eos(slope=.7):
    p=np.geomspace(1e-9,1e-7,50)
    e=2e-8+slope*p
    return p,e,Candidate(p,e,cap=.99,alpha=.6)

class SourceAuditTests(unittest.TestCase):
    def test_original_acausal_secants_visible_and_lift_stays_separate(self):
        p,e,c=eos()
        d,rows=source_comparison(p,e,c,float(c.e[30]))
        self.assertEqual(d["source_original_superluminal_secant_segments"],len(p)-1)
        self.assertGreater(d["source_original_max_secant_cs2_over_c2"],1)
        self.assertLessEqual(d["candidate_max_secant_cs2_over_c2"],.99+1e-9)
        self.assertGreater(d["source_energy_changed_knots"],0)
        self.assertTrue(d["F53_comparison_star_not_rerun"])
        self.assertIn("NOT_SOLVED",d["source_original_star_at_this_pressure"])
        self.assertEqual(len(rows),50)
    def test_original_causal_has_no_artificial_lift(self):
        p,e,c=eos(slope=2)
        d,_=source_comparison(p,e,c,float(c.e[30]))
        self.assertEqual(d["source_original_superluminal_secant_segments"],0)
        self.assertEqual(d["source_energy_changed_knots"],0)
        self.assertAlmostEqual(d["source_energy_max_fractional_lift"],0)
    def test_center_pressure_exact_on_tabulated_node(self):
        p,e,c=eos()
        d,_=source_comparison(p,e,c,float(c.e[30]))
        self.assertAlmostEqual(d["F53_candidate_center_pressure_geom_m_minus_2"]/p[30],1,places=12)
        self.assertGreater(d["F53_center_original_vs_candidate_density_shift_at_equal_pressure_fraction"],0)
    def test_source_firstlaw_increments_monotone(self):
        p,e,c=eos()
        x=source_thermo(p,e)
        self.assertTrue(np.all(np.diff(x["h"])>0))
        self.assertTrue(np.all(x["n"]>0))
    def test_source_density_nonmonotonicity_fails_closed(self):
        p,e,c=eos()
        e[10]=e[9]
        with self.assertRaisesRegex(ValueError,"UNMODIFIED_SOURCE_NONMONOTONIC"):
            source_thermo(p,e)
    def test_missing_candidate_center_support_fails_closed(self):
        p,e,c=eos()
        with self.assertRaisesRegex(ValueError,"ENERGY_OUTSIDE"):
            source_comparison(p,e,c,float(c.e[-1]*2))
    def test_native_cs2_field_not_substituted_for_secants(self):
        p,e,c=eos()
        d,_=source_comparison(p,e,c,float(c.e[25]),np.linspace(.1,1.2,len(p)))
        self.assertEqual(d["JESTER_native_cs2_field_statistics"]["size"],len(p))
        self.assertGreater(d["JESTER_native_cs2_field_statistics"]["count_reported_gt_1_if_dimensionless"],0)
        self.assertGreater(d["source_original_max_secant_cs2_over_c2"],1)
    def test_source_lift_is_not_global_nuclear_eos_proof(self):
        p,e,c=eos()
        d,_=source_comparison(p,e,c,float(c.e[25]))
        self.assertFalse(d["global_physical_WFF1_EOS_causality_proven"])
        self.assertEqual(d["global_dynamical_stability"],"NOT_TESTED")
        self.assertEqual(d["XPSI_15D_source_native_Bayes"],"NOT_RUN")

if __name__=="__main__":
    unittest.main()
