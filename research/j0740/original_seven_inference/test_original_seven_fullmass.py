"""Real source-locked and adversarial acceptance tests, original seven static EOS."""
import io,json,sys,unittest,zipfile
from pathlib import Path
import numpy as np
from scipy.stats import truncnorm
from scipy.integrate import simpson
sys.path.insert(0,str(Path(__file__).parent))
from original_seven_fullmass_integral import (
 PINNED_NPZ_SHA,PINNED_F38_SHA,PINNED_SEVEN_SHA,sha,density,
 load_eos,load_surface,model_integration,xpsi_source_support,M_LOW,M_HIGH,run)
ROOT=Path(__file__).parent
EOS=ROOT/'J0740_seven_original_EOS_source_arrays_20261119.zip'
F38=ROOT/'J0740_F38_Source_Marginal_Likelihood_20261117.zip'

class OriginalEvidenceTests(unittest.TestCase):
 def test_archive_exact_source_hashes(self):
  self.assertEqual(sha(EOS),PINNED_SEVEN_SHA)
  self.assertEqual(sha(F38),PINNED_F38_SHA)
 def test_source_all_seven_exact_labels_and_sha(self):
  with zipfile.ZipFile(EOS) as z:
   self.assertEqual(set(z.namelist()),{k+'.npz' for k in PINNED_NPZ_SHA}|{'source_manifest.json'})
   for k in PINNED_NPZ_SHA:
    curve,mmax,r073,h=load_eos(z,k)
    self.assertEqual(h,PINNED_NPZ_SHA[k]);self.assertGreater(mmax,2.1)
    self.assertTrue(9.<r073<16.)
    self.assertTrue(np.isfinite(curve(2.073)))
 def test_source_prior_mass_normalization(self):
  m=np.linspace(M_LOW,M_HIGH,2001)
  self.assertAlmostEqual(simpson(density(m),x=m),1,places=8)
  self.assertTrue(xpsi_source_support([2.082],[12.])[0])
  self.assertFalse(xpsi_source_support([2.082],[16.01])[0])
  self.assertFalse(xpsi_source_support([2.082],[7.])[0])
 def test_constant_likelihood_over_full_m_support_returns_one(self):
  curve=lambda m:np.full_like(m,12.0)
  fake=lambda pts:np.ones(len(pts))
  v=model_integration(curve,3.0,fake,n=4001)
  self.assertAlmostEqual(v['value'],1,places=7)
  self.assertAlmostEqual(v['source_support_prior_probability'],1,places=7)
 def test_mass_above_static_tov_integrated_as_no_star(self):
  curve=lambda m:np.full_like(m,12.0)
  fake=lambda pts:np.ones(len(pts))
  cutoff=2.1136703143450717
  v=model_integration(curve,cutoff,fake,n=4001)
  mass=truncnorm.cdf(cutoff,-5,5,loc=2.082,scale=.0703)
  self.assertAlmostEqual(v['value'],mass,places=7)
  self.assertAlmostEqual(v['upper_truncated_radio_prior_mass'],1-mass,places=7)
 def test_all_six_source_surfaces_prevent_prior_support_leak(self):
  with zipfile.ZipFile(F38) as z:
   keys=[x.split('posterior_prior_ratio_')[1].split('.npz')[0] for x in z.namelist() if x.startswith('posterior_prior_ratio_')]
   self.assertEqual(len(keys),6)
   for k in keys:
    fit,upper=load_surface(z,k)
    self.assertGreater(upper,0)
    self.assertEqual(float(fit([[2.082,25.]])[0]),0.)
 def test_six_full_scores_model_posteriors_normalize(self):
  d=run(EOS,F38,ROOT/'test_results')
  self.assertEqual(set(d['summary']),set(PINNED_NPZ_SHA))
  for k,x in d['six_F38_KDE_surfaces'].items():
   self.assertAlmostEqual(sum(v['equal_discrete_model_prior_posterior_conditioned_on_static_source_model_set'] for v in x['model_scores'].values()),1.,places=12)
   self.assertGreater(x['model_scores']['MPA1']['value'],x['model_scores']['ENG']['value'])
 def test_quadrature_convergence_real_eos_and_source(self):
  with zipfile.ZipFile(EOS) as ez,zipfile.ZipFile(F38) as fz:
   func,mmax,_,_=load_eos(ez,'APR4_EPP')
   fit,_=load_surface(fz,'weighted_0.025_0.35')
   vals=[model_integration(func,mmax,fit,n=n)['value'] for n in (1001,2001,4001,8001)]
   self.assertLess(abs(vals[-1]/vals[-2]-1),.0005)
   self.assertLess(abs(vals[-1]/vals[0]-1),.002)
 def test_reject_wrong_orig_eos_file_content(self):
  with zipfile.ZipFile(EOS) as z:
   data=z.read('MPA1.npz')
   bad=data[:-1]+bytes([data[-1]^1])
   tampered=io.BytesIO()
   with zipfile.ZipFile(tampered,'w') as out:
    out.writestr('MPA1.npz',bad)
   tampered.seek(0)
   with zipfile.ZipFile(tampered) as out:
    with self.assertRaisesRegex(ValueError,'original NPZ SHA mismatch'):
     load_eos(out,'MPA1')


if __name__=='__main__':unittest.main(verbosity=2)
