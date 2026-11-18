"""F56 source physics sanity gates; mock arrays are not observational EOS."""
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f56_wff1_original_vs_lifted_source import rising_branch_radius,Candidate


class NativeWFF1AuditTests(unittest.TestCase):
    def native_curve(self):
        mass=np.linspace(.1,2.2,500)
        radius=14.0 - 2.0 * (mass-.1)/(2.2-.1)
        return mass,radius

    def test_only_unique_stable_bracket_interpolated(self):
        m,r=self.native_curve()
        x=rising_branch_radius(m,r,2.073)
        self.assertAlmostEqual(x["rising_branch_interpolated_radius_km"],12.121,places=2)
        self.assertTrue(x["only_local_MR_interpolation_not_new_star"])
        self.assertTrue(x["source_TOV_max_is_LAST_SAMPLED_NOT_PROVEN_GLOBAL"])

    def test_never_calls_last_MR_sample_global_stable_max(self):
        m,r=self.native_curve()
        m[-1]=m[-2]-.01
        x=rising_branch_radius(m,r,2.073)
        self.assertFalse(x["source_TOV_max_is_LAST_SAMPLED_NOT_PROVEN_GLOBAL"])

    def test_unbracketed_mass_fails(self):
        m,r=self.native_curve()
        with self.assertRaisesRegex(ValueError,"NO_UNIQUE"):
            rising_branch_radius(m,r,4.)

    def test_duplicate_ascending_crossing_fails(self):
        m,r=self.native_curve()
        # M rises through target, declines below, then rises again above target.
        m[470:480]=1.9
        m[480:]=np.linspace(1.9,2.3,len(m)-480)
        with self.assertRaises(ValueError):
            rising_branch_radius(m,r,2.073)

    def test_bad_radius_units_rejected(self):
        m,r=self.native_curve()
        with self.assertRaisesRegex(ValueError,"SHAPE_OR_UNITS"):
            rising_branch_radius(m,r*1000.,2.073)

    def test_mathematical_causal_lift_changes_energy_not_source(self):
        p=np.geomspace(1.,100.,100)
        e=p*.60+10
        original=e.copy()
        model=Candidate(p,e,cap=.90,alpha=.6)
        self.assertTrue(np.array_equal(e,original))
        self.assertGreater(np.max((model.e-e)/e),0)
        self.assertLessEqual(np.max(model.cs2),.90*(1+1e-9))

    def test_mixed_source_profile_is_not_silently_clipped(self):
        p=np.geomspace(.1,10.,70)
        e=p*.5+10.
        e[15]=e[14]-.1
        c=Candidate(p,e,cap=.99)
        self.assertLessEqual(np.max(c.cs2),.99+1e-9)
        self.assertEqual(e[15]<e[14],True)

if __name__=="__main__":
    unittest.main()
