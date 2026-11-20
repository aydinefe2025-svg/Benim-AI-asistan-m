from __future__ import annotations
import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import f75_prior_corrected_flow_gr_integrals as f

class F75Tests(unittest.TestCase):
    def test_source_prior_mass_factor_cancels_target_mass_once(self):
        m=np.linspace(1.89,2.10,12)
        r=np.full_like(m,12.5)
        pi=f.source_pi_eff(m,r)
        ratio=f.mass_pdf(m)/pi
        self.assertTrue(np.all(pi>0))
        self.assertTrue(np.allclose(ratio,(f.R_HI-f.R_LO)*f.Z_STAR,rtol=2e-12,atol=0))

    def test_prior_support_is_hard(self):
        m=np.array([2.0,2.0,1.0])
        rc=f.critical_radius(2.0)
        r=np.array([rc-1e-3,16.001,12.0])
        got=f.source_pi_eff(m,r)
        self.assertEqual(got[0],0.0)
        self.assertEqual(got[1],0.0)
        self.assertEqual(got[2],0.0)

    def test_critical_radius_satisfies_source_polar_cut(self):
        for m in (1.89,2.0,2.10):
            r=f.critical_radius(m)
            z=f.RG_KM*m/r
            eps=(2*np.pi*f.FREQ_HZ)**2*(r*1000)**3/(f.RG_KM*1000*m*f.C_M_S**2)
            self.assertAlmostEqual(r*(1+eps*(-.788+1.030*z)),3.01*f.RG_KM*m,places=9)

    def test_kde_normalizes_after_native_support(self):
        rng=np.random.default_rng(20261119)
        m=rng.normal(2.08,.06,100000)
        r=rng.normal(12.5,.7,100000)
        mg,rg,q,interp,d=f.build_kde(m,r,.018,.25,n=120)
        self.assertAlmostEqual(float(np.sum(q)*(mg[1]-mg[0])*(rg[1]-rg[0])),1.0,10)
        self.assertGreaterEqual(d['integral_after_hard_support'],.999999999)
        self.assertTrue(np.isfinite(interp([[2.0,12.0]])[0]))

    def test_mass_density_outside_source_support_is_zero(self):
        self.assertEqual(float(f.mass_pdf(1.0)),0.0)
        self.assertGreater(float(f.mass_pdf(2.0)),0.0)

if __name__=="__main__":unittest.main()
