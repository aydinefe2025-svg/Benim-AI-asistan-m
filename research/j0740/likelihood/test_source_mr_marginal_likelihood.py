import unittest, numpy as np
from scipy.stats import truncnorm
from source_mr_marginal_likelihood import grid_geometry,fit,point,source_mr_support,M_MU,M_SIG,R_MIN_KM,R_MAX_KM,S_MR
class SourceLikelihoodTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  rng=np.random.default_rng(20261117)
  m=truncnorm.rvs(-5,5,loc=M_MU,scale=M_SIG,size=200000,random_state=rng)
  r=rng.uniform(R_MIN_KM,R_MAX_KM,len(m))
  sel=source_mr_support(m,r);m=m[sel];r=r[sel]
  cls.mass=m;cls.radius=r
  cls.geom=grid_geometry()
  cls.w_uniform=np.full(len(m),1/len(m))
  cls.w_signal=np.exp(-.5*((r-12.8)/.9)**2)
  cls.w_signal/=cls.w_signal.sum()
  cls.q=fit(m,r,cls.w_signal,cls.geom,.025,.35)
 def test_prior_grid_normalized(self):
  *_,dm,dr,mask,prior,raw=self.geom
  self.assertLess(abs(raw-1),.003)
  self.assertLess(abs(prior.sum()*dm*dr-1),1e-11)
  self.assertTrue(np.all(prior[~mask]==0))
 def test_source_support_and_zeros(self):
  self.assertTrue(self.q['zero_support_leakage'])
  self.assertEqual(point(2.08,8.5,self.q,self.geom)['status'],'OUTSIDE_SOURCE_SUPPORT')
  self.assertAlmostEqual(self.q['normalization_check'],1,places=11)
 def test_synthetic_likelihood_recovery(self):
  # Ratio is a *bandwidth-smoothed* approximation to injected signal; verify broad trend.
  hi=point(2.08,12.8,self.q,self.geom)['likelihood_ratio']
  lo=point(2.08,11.0,self.q,self.geom)['likelihood_ratio']
  self.assertGreater(hi/lo,3)
  self.assertLess(hi/lo,16)
 def test_flat_source_prior_recovery(self):
  q=fit(self.mass,self.radius,self.w_uniform,self.geom,.025,.35)
  vals=[point(2.08,x,q,self.geom)['likelihood_ratio'] for x in (10.8,12.8,14.2)]
  self.assertLess(max(vals)/min(vals),1.22)
 def test_cutoff_no_extrapolation(self):
  self.assertTrue(np.all(source_mr_support(self.mass,self.radius)))
  self.assertEqual(point(2.08,16.4,self.q,self.geom)['status'],'OUTSIDE_SOURCE_SUPPORT')
if __name__=='__main__':unittest.main(verbosity=2)