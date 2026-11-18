"""F51 source-integrity, numerical and failing-gate regression suite."""
from __future__ import annotations
import copy, math, tempfile, unittest
from pathlib import Path
import sys
import numpy as np
from scipy.integrate import simpson
sys.path.insert(0,str(Path(__file__).resolve().parent))
import f51_extended_support_audit as f

class F51Tests(unittest.TestCase):
 def test_prior_old_window_from_f49(self):
  self.assertAlmostEqual(f.prior_probability(1.95,2.10),.5708291253531559,11)
 def test_new_coverage(self):
  self.assertAlmostEqual(f.prior_probability(1.89,2.10),.597886832314311,11)
  self.assertGreater(f.prior_probability(1.89,2.1),f.prior_probability(1.95,2.1))
 def test_positive_mass_tail(self):
  self.assertGreater(1-f.prior_probability(1.89,2.10),.40)
 def test_pdf_normalized_on_five_sigma(self):
  m=np.linspace(f.MU-5*f.SIG,f.MU+5*f.SIG,5001)
  self.assertAlmostEqual(float(simpson(f.prior_pdf(m),x=m)),1.,5)
 def test_mass_filter_nonzero_stellar_residual(self):
  s={'mass_msun':2.073,'spin_hz':f.SPIN,'radius_eq_km':11.,
     'central_energy_density_g_cm3':1.2e15,'axis_ratio':.99}
  f.validate_star(s,2.073)
  t={**s,'mass_msun':2.083}
  with self.assertRaisesRegex(ValueError,'BAD_DIRECT_RNS_ROOT'):f.validate_star(t,2.073)
 def test_frequency_mismatch(self):
  s={'mass_msun':2.073,'spin_hz':f.SPIN+.011,'radius_eq_km':11.,
     'central_energy_density_g_cm3':1.2e15,'axis_ratio':.99}
  with self.assertRaisesRegex(ValueError,'BAD_DIRECT_RNS_ROOT'):f.validate_star(s,2.073)
 def test_causal_input_hash_rejects_corrupted_archive(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'notzip.zip';p.write_bytes(b'untrusted')
   with self.assertRaisesRegex(ValueError,'BAD_SHA256_'):f.source_zip(p,'WFF1')
 def test_f38_grid_missing_corner_refused(self):
  mg=np.linspace(1.7,2.5,401);rg=np.linspace(4,16,581)
  L=np.ones((401,581));mask=np.ones((401,581),bool)
  m=np.array([2.05]);r=np.array([12.])
  i=np.searchsorted(mg,m,side='right')[0]-1
  j=np.searchsorted(rg,r,side='right')[0]-1
  mask[i,j]=False
  with self.assertRaisesRegex(ValueError,'F38_HARD_SOURCE_SUPPORT'):
   f.sample(mg,rg,L,mask,m,r)
 def test_integral_analytic_prior_and_constant_likelihood(self):
  m=np.linspace(1.89,2.10,1801)
  out=f.integral(m,np.ones_like(m))
  self.assertAlmostEqual(out['likelihood_full_radio_prior_window_contribution'],f.prior_probability(1.89,2.1),7)
  self.assertAlmostEqual(out['conditional_on_verified_mass_window_L_over_Z'],1.,7)
 def test_integral_nonmonotone_refused(self):
  m=np.linspace(1.89,2.10,16);m[3]=m[2]
  with self.assertRaisesRegex(ValueError,'INVALID_MASSES'):f.integral(m,np.ones(16))
 def test_supported_models_seven_unchanged(self):
  self.assertEqual(len(f.EOS),7)
  self.assertEqual(f.TOP['WFF1'],2.10)
  self.assertEqual(f.TOP['WFF2'],2.175)
 def test_radio_prior_once(self):
  m=np.linspace(1.89,2.1,1801)
  out=f.integral(m,np.full_like(m,2.))
  self.assertAlmostEqual(out['conditional_on_verified_mass_window_L_over_Z'],2.,6)

if __name__=='__main__':unittest.main()
