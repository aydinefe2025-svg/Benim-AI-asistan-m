import unittest,tempfile,json
from pathlib import Path
import numpy as np
import sys
sys.path.insert(0,str(Path(__file__).parent))
import f47_mass_integrated_source_likelihood as f
from scipy.integrate import simpson

class Tests(unittest.TestCase):
 def test_p_window_between_zero_one(self):self.assertTrue(.5<f.prior_window_probability()<.6)
 def test_constant_likelihood_integrates_one_conditioned(self):
  m=np.linspace(f.M0,f.M1,23)
  result=f.integrate_curve(m,np.ones_like(m))
  self.assertAlmostEqual(result['conditional_on_common_window_source_Z_ratio'],1,places=5)
 def test_zero_likelihood(self):
  m=np.linspace(f.M0,f.M1,23)
  self.assertAlmostEqual(f.integrate_curve(m,np.zeros_like(m))['conditional_on_common_window_source_Z_ratio'],0)
 def test_linearly_scaled_likelihood(self):
  m=np.linspace(f.M0,f.M1,25)
  x=f.integrate_curve(m,np.ones_like(m));y=f.integrate_curve(m,np.ones_like(m)*3)
  self.assertAlmostEqual(y['conditional_on_common_window_source_Z_ratio']/x['conditional_on_common_window_source_Z_ratio'],3)
 def test_reject_incomplete_mass_window(self):
  with self.assertRaisesRegex(ValueError,'INTEGRAND_NOT_FULL_DECLARED_WINDOW'):
   f.integrate_curve(np.linspace(1.96,2.10,23),np.ones(23))
 def test_reject_negative_likelihood(self):
  m=np.linspace(f.M0,f.M1,23);y=np.ones_like(m);y[6]=-1
  with self.assertRaises(ValueError):f.integrate_curve(m,y)
 def test_support_grid_sampling_one(self):
  mm=np.linspace(1.5,2.5,11);rr=np.linspace(8,20,13)
  z=np.ones((11,13));s=np.ones_like(z,dtype=bool)
  x=f.sample_masked(mm,rr,z,s,np.array([2.,2.05]),np.array([11,12]))
  self.assertTrue(np.array_equal(x,[1,1]))
 def test_support_mask_corner_rejection(self):
  mm=np.linspace(1.5,2.5,11);rr=np.linspace(8,20,13)
  z=np.ones((11,13));s=np.ones_like(z,dtype=bool);s[5,3]=False;z[5,3]=0
  with self.assertRaisesRegex(ValueError,'HARD_SUPPORT_MASK'):
   f.sample_masked(mm,rr,z,s,np.array([2.01]),np.array([11.2]))
 def test_grid_no_extrapolation(self):
  mm=np.linspace(1.5,2.5,11);rr=np.linspace(8,20,13)
  z=np.ones((11,13));s=np.ones_like(z,dtype=bool)
  with self.assertRaisesRegex(ValueError,'OUTSIDE_GRID'):
   f.sample_masked(mm,rr,z,s,np.array([2.01]),np.array([30.2]))
 def test_source_pins(self):self.assertEqual(len(f.EOS),7);self.assertEqual(len(f.F38_SHA),64)
 def test_wrong_f44_archive_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'f44.zip';path.write_bytes(b'corrupt')
   with self.assertRaisesRegex(ValueError,'F44_ANCHOR_ARCHIVE_SHA_MISMATCH'):
    f.validate_all_curves(Path(d),path)
 def test_radiomass_pdf_integral_full(self):
  m=np.linspace(f.MU-5*f.SIG,f.MU+5*f.SIG,1001)
  self.assertAlmostEqual(simpson(f.full_radio_pdf(m),x=m),1,places=5)
if __name__=='__main__':unittest.main(verbosity=2)
