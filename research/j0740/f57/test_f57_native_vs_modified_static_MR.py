"""F57 static source M-R interpolation tests; synthetic sequences aren't stars."""
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f57_native_vs_modified_static_MR import stable_native_radius,INTERP_TOL_KM


def sample():
    m=np.linspace(.4,2.3,200)
    r=15-1.5*m
    return m,r


class SourceStaticTests(unittest.TestCase):
    def test_rising_branch_exact_linear_radius(self):
        m,r=sample()
        d=stable_native_radius(m,r,2.073)
        self.assertAlmostEqual(d["pchip_local_native_radius_km"],15-1.5*2.073,places=9)
        self.assertLess(d["interpolation_method_spread_km"],INTERP_TOL_KM)
        self.assertTrue(d["native_peak_at_last_sample_not_global_max_proof"])

    def test_peak_inside_does_not_assert_global_stability(self):
        m,r=sample()
        m[-1]=m[-2]-.05
        d=stable_native_radius(m,r,2.073)
        self.assertFalse(d["native_peak_at_last_sample_not_global_max_proof"])
        self.assertFalse(d["physical_source_EOS_causality_certified"])

    def test_unavailable_mass_fails(self):
        m,r=sample()
        with self.assertRaisesRegex(ValueError,"NO_UNIQUE"):
            stable_native_radius(m,r,4)

    def test_nonmonotonic_near_target_fails(self):
        m,r=sample()
        i=np.searchsorted(m,2.073)
        m[i-2]=m[i-1]+.01
        with self.assertRaisesRegex(ValueError,"NONMONOTONIC"):
            stable_native_radius(m,r,2.073)

    def test_wrong_radii_unit_rejected(self):
        m,r=sample()
        with self.assertRaisesRegex(ValueError,"ARRAY_OR_RADIUS_UNITS"):
            stable_native_radius(m,1000*r,2.073)

    def test_nonfinite_rejected(self):
        m,r=sample()
        r[7]=float("nan")
        with self.assertRaisesRegex(ValueError,"ARRAY_OR_RADIUS_UNITS"):
            stable_native_radius(m,r,2.073)

    def test_equal_end_point_not_claimed_interior(self):
        m,r=sample()
        with self.assertRaisesRegex(ValueError,"SOURCE_TARGET_ENDPOINT_NOT_INTERIOR"):
            stable_native_radius(m,r,float(m[160]))

if __name__=="__main__":unittest.main()
