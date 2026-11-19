import math
import tempfile
import unittest
from pathlib import Path
import numpy as np
from f67_mpa1_pchip_firstlaw_tov import ColdEOS, load_source, tov, sha, EOS_LABEL

class TestF67(unittest.TestCase):
    def setUp(self):
        self.p=np.geomspace(1e-34,3e-9,102)
        self.e=1e-9*(self.p/2e-10)**.62
        self.table=np.c_[self.p,self.e]
    def test_01_separate_identity(self):
        self.assertIn('NOT_ORIGINAL',EOS_LABEL)
        self.assertNotEqual(EOS_LABEL,'MPA1')
    def test_02_raw_monotone(self):
        s=ColdEOS(self.table)
        self.assertEqual(s.knots,102)
    def test_03_negative_raw_fails(self):
        bad=self.table.copy();bad[20,1]=0
        with self.assertRaises(ValueError):ColdEOS(bad)
    def test_04_source_wrong_sha_fails(self):
        with tempfile.TemporaryDirectory() as p:
            src=Path(p)/'MPA1.dat';np.savetxt(src,self.table)
            with self.assertRaisesRegex(ValueError,'SHA_DRIFT'):load_source(src)
    def test_05_bad_source_shape_fails(self):
        with tempfile.TemporaryDirectory() as p:
            src=Path(p)/'MPA1.dat';np.savetxt(src,self.table[:20])
            with self.assertRaises(ValueError):load_source(src,require_original=False)
    def test_06_no_negative_cold_enthalpy(self):
        s=ColdEOS(self.table)
        self.assertGreater(s.hmax,0)
        self.assertTrue((np.diff(s.h)>0).all())
    def test_07_pchip_interpolates_exact_source(self):
        s=ColdEOS(self.table)
        x=np.log(self.p)
        self.assertLess(np.max(np.abs(s.spline(x)-np.log(self.e))),2e-12)
    def test_08_positive_causality_sample(self):
        s=ColdEOS(self.table)
        chk=s.sound_speed_screen(1e-10)
        self.assertEqual(chk['sampled_cs2_nonpositive_count'],0)
        self.assertTrue(chk['sampled_entire_star_eos_causal'])
    def test_09_exact_chemical_potential_identity(self):
        s=ColdEOS(self.table)
        x=s.x[3:-4:14];h=s.inverse_enthalpy_from_logp(x)
        n=s.n_ratio(x,h);e=np.exp(s.spline(x));p=np.exp(x)
        self.assertLess(np.max(np.abs((e+p)/(s.e0p0*n*np.exp(h))-1)),5e-13)
    def test_10_independent_first_law_slope(self):
        s=ColdEOS(self.table)
        x=float(s.x[len(s.x)//2]);dx=1e-4
        lp=lambda a:math.log(float(s.n_ratio(np.array([a]))[0]))
        actual=(lp(x+dx)-lp(x-dx))/(2*dx)
        e=math.exp(s.spline(x));p=math.exp(x)
        expected=float(s.spline(x,1))*e/(e+p)
        self.assertLess(abs(actual-expected),2e-5)
    def test_11_two_tov_methods_independent(self):
        s=ColdEOS(self.table)
        a=tov(s,1e-10,method='rm');b=tov(s,1e-10,method='uv')
        self.assertLess(abs(a['R_km']-b['R_km'])/a['R_km'],5e-5)
        self.assertLess(abs(a['M_msun']-b['M_msun'])/a['M_msun'],5e-5)
    def test_12_subdivision_convergence(self):
        a=ColdEOS(self.table,subdivisions=12,quadrature=32)
        b=ColdEOS(self.table,subdivisions=24,quadrature=48)
        s=tov(a,1e-10);t=tov(b,1e-10)
        self.assertLess(abs(s['R_km']-t['R_km']),.025)
    def test_13_bad_central_pressure(self):
        s=ColdEOS(self.table)
        with self.assertRaises(ValueError):tov(s,s.pmax*1.1)
    def test_14_invalid_method_fails(self):
        s=ColdEOS(self.table)
        with self.assertRaises(ValueError):tov(s,1e-10,method='xyz')
    def test_15_n_over_n0_at_source_min(self):
        s=ColdEOS(self.table)
        self.assertAlmostEqual(float(s.n_ratio(np.array([math.log(s.p0)]))[0]),1,places=13)
    def test_16_status_is_not_original(self):
        self.assertIn('EXPLORATORY',EOS_LABEL)

if __name__=='__main__':unittest.main()