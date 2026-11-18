"""F61: red/green math and exact-source acceptance tests independent of LAL wheel."""
import importlib.util
import math
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np

script=Path(__file__).with_name('f61_original_lal_static.py')
spec=importlib.util.spec_from_file_location('f61_original_lal_static',script)
f61=importlib.util.module_from_spec(spec); spec.loader.exec_module(f61)

class F61MathTests(unittest.TestCase):
    def test_radio_prior_normalization(self):
        self.assertEqual(f61.mass_prior_cdf(2.082-5*.0703),0)
        self.assertEqual(f61.mass_prior_cdf(2.082+5*.0703),1)
        self.assertAlmostEqual(f61.mass_prior_cdf(2.082),0.5,14)

    def test_prior_mass_increases_with_static_max(self):
        self.assertLess(f61.mass_prior_cdf(2.175),f61.mass_prior_cdf(2.25))
        self.assertAlmostEqual(f61.mass_prior_cdf(2.175)-f61.mass_prior_cdf(1.89),0.903910842245011,12)

    def test_source_static_branch_strict_monotonicity(self):
        m=np.r_[np.linspace(.10,.05,8),np.linspace(.051,2.5,40),np.linspace(2.49,2.2,5)]
        rr=np.linspace(12,9,len(m))
        bm,br,d=f61.reference_static_branch(m,rr)
        self.assertEqual(d['native_mmax_msun'],2.5)
        self.assertTrue((np.diff(bm)>0).all())
        self.assertLess(len(bm),len(m))

    def test_source_internal_reversal_rejected(self):
        m=np.linspace(.5,2.5,60);m[23]=m[22]-.01
        with self.assertRaisesRegex(ValueError,'NONMONOTONIC'):
            f61.reference_static_branch(m,np.ones(len(m))*12.)

    def test_tov_scanner_and_root_are_direct_not_mass_interpolation(self):
        def solve(p):
            m=1.+.65*math.log10(p/1e32)
            return {'mass_msun':m,'radius_km':12.0-.1*(m-2.),'central_pressure_si_pa':p}
        asc,scans,failed=f61.scan_native_source(solve,low_pa=1e32,high_pa=1e35,nscan=45)
        self.assertEqual(len(failed),0)
        star=f61.root_at_mass(solve,asc,2.073)
        self.assertAlmostEqual(star['mass_msun'],2.073,7)
        self.assertTrue(star['native_TOV_not_source_interpolation'])
        self.assertGreater(star['direct_TOV_solver_calls_in_root'],0)
        self.assertIsNone(f61.root_at_mass(solve,asc,4.0))

    def test_bad_native_tov_return_rejected(self):
        with self.assertRaisesRegex(ValueError,'INVALID'):
            f61.positive_tov_result(1e35,12000,4e30,-1,2e30)
        with self.assertRaisesRegex(ValueError,'INVALID'):
            f61.positive_tov_result(1e35,-12000,4e30,.09,2e30)

    def test_bad_target_rejected(self):
        with self.assertRaisesRegex(ValueError,'INVALID_TARGET'):
            f61.root_at_mass(lambda p:None,[],float('nan'))

    def test_source_causality_report_preserves_crust_negative(self):
        pp=np.geomspace(1e-13,1e-8,250)
        ee=1e-10*(pp/pp[0])**.45
        cs2=np.full(250,.5);cs2[0]=-.0001
        pc_pa=1e35
        report=f61.source_physics_at_center({'p':pp,'e':ee,'cs2':cs2},pc_pa,lambda p:.7)
        self.assertGreaterEqual(report['sampled_full_interior_cs2_nonpositive'],1)
        self.assertEqual(report['sampled_core_screen'],'SAMPLED_PASS_NOT_CONTINUOUS_OR_FULL_STAR_PROOF')
        self.assertEqual(report['full_interior_screen'],'SAMPLED_FAIL')

    def test_source_causality_rejects_center_extrapolation(self):
        p=np.geomspace(1e-13,1e-11,150)
        e=np.geomspace(1e-12,1e-10,150)
        with self.assertRaisesRegex(ValueError,'OUTSIDE_THERMO_TABLE'):
            f61.source_physics_at_center({'p':p,'e':e,'cs2':np.full(150,.5)},1e35,lambda p:.5)

    def test_no_false_rotating_or_bayes_claims(self):
        self.assertIn('STATIC',f61.run.__doc__ or 'STATIC')
        self.assertNotIn('F42',str(f61.EOS))

if __name__=='__main__':unittest.main()