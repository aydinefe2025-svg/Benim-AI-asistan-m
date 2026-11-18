"""F65 native-source precise physics/claim gates without mocking final results."""
import unittest, numpy as np, tempfile, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from f65_native_crust_derivative_map import (classify_scan,validate_original,source_analytic_bridge,
         EOS,SHARED_BAD,GRID_N, P_LEFT,P_RIGHT,evaluate_lal)

class FakeLAL:
    def SimNeutronStarEOSEnergyDensityOfPressureGeometerized(self,p,eos):return p+1
    def SimNeutronStarEOSEnergyDensityDerivOfPressureGeometerized(self,p,eos):return 1.

class Tests(unittest.TestCase):
    def setUp(self):
        self.p=np.linspace(1,3,121)
        self.e=1+np.cumsum(np.r_[0,np.ones(120)*.02])
        self.d=np.ones(121)
    def test_native_seven_exact(self):self.assertEqual(len(EOS),7)
    def test_expected_shared_six(self):self.assertEqual(SHARED_BAD,set(EOS)-{'APR4_EPP'})
    def test_scan_minimum(self):self.assertEqual(GRID_N,1201)
    def test_pressure_window_contains_source(self):self.assertTrue(P_LEFT<5.175111469637044e-16<P_RIGHT)
    def test_good_scan(self):
        x=classify_scan(self.p,self.e,self.d,source_idx=254,source_negative=False)
        self.assertEqual(x['negative_inverse_cs2_sample_nodes'],0)
        self.assertEqual(x['negative_energy_secant_bins'],0)
    def test_detects_negative_finite_interval(self):
        d=self.d.copy();d[43:48]=-2.; e=self.e.copy();e[43:48]-=.1
        x=classify_scan(self.p,e,d,source_idx=254,source_negative=True)
        self.assertEqual(x['negative_inverse_cs2_sample_nodes'],5)
        self.assertEqual(len(x['analytic_derivative_sign_change_brackets']),2)
    def test_bad_p_monotone_rejected(self):
        p=self.p.copy();p[3]=p[2]
        with self.assertRaisesRegex(ValueError,'PHYSICS_GUARD'):classify_scan(p,self.e,self.d,source_idx=254,source_negative=False)
    def test_bad_e_rejected(self):
        e=self.e.copy();e[3]=-1
        with self.assertRaisesRegex(ValueError,'PHYSICS_GUARD'):classify_scan(self.p,e,self.d,source_idx=254,source_negative=False)
    def test_bad_d_rejected(self):
        d=self.d.copy();d[5]=0
        with self.assertRaisesRegex(ValueError,'PHYSICS_GUARD'):classify_scan(self.p,self.e,d,source_idx=254,source_negative=False)
    def test_bad_nan_rejected(self):
        d=self.d.copy();d[5]=np.nan
        with self.assertRaisesRegex(ValueError,'PHYSICS_GUARD'):classify_scan(self.p,self.e,d,source_idx=254,source_negative=False)
    def test_bad_n_rejected(self):
        with self.assertRaisesRegex(ValueError,'BAD_SCAN_ARRAYS'):classify_scan(self.p[:20],self.e[:20],self.d[:20],source_idx=254,source_negative=False)
    def test_lal_evaluator_independent(self):
        e,d=evaluate_lal(2.,None,FakeLAL());self.assertEqual(e,3.);self.assertEqual(d,1.)
    def test_reject_wrong_source_sha(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/'wrong.npz';p.write_text('wrong')
            with self.assertRaisesRegex(ValueError,'SHA_MISMATCH'):validate_original(p,'a'*64,836)
    def test_reject_source_bridge_mismatch(self):
        x={'p':self.p,'e':self.e,'cs2':np.ones(121)}
        with self.assertRaisesRegex(ValueError,'SOURCE_VALUE_DRIFT'):source_analytic_bridge(x,None,FakeLAL(),indices=(30,40,50))
    def test_scan_doesnt_claim_eos_cert(self):
        x=classify_scan(self.p,self.e,self.d,source_idx=254,source_negative=False)
        self.assertTrue(x['finite_scan_is_not_continuous_physical_certificate'])

if __name__=='__main__':unittest.main()