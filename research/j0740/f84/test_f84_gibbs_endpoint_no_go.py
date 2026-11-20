import unittest,math,numpy as np
from pathlib import Path
import f84_gibbs_endpoint_no_go as F

class TestF84NativeGibbs(unittest.TestCase):
 def setUp(self):
  self.R=Path(__file__).resolve().parent/'F83_PIECEWISE_COLD_BPS_MPA1_SOURCE_P_E.rns'
  self.E,self.P,self.H,self.n,self.mu0=F.source_f83(self.R)
  # Three exactly source-native BPS knots from original a419... CSV.
  self.pts=np.array([
   [.027199999999999998,.072397332824260377,25.688892037517],
   [.028199999999999999,.076310910572544272,26.635997445195386],
   [.079200000000000007,.36918421837903626,75.092556448359261]])
 def test_real_exact_source_regenerates_mu0(self):self.assertAlmostEqual(self.mu0,930.4,places=9)
 def test_native_join_bracket_no_interpolation(self):
  n,p,e=self.pts.T;b=F.match_bound(F.JOIN_P,n,p,e)
  self.assertAlmostEqual(b['mu_BPS_at_join_lower_bound_MeV'],947.2028730345028,places=9)
  self.assertAlmostEqual(b['mu_BPS_at_join_upper_bound_MeV'],947.2064262030219,places=9)
 def test_new_f83_at_actual_join_is_undercalibrated(self):
  x=F.cold_mu(F.JOIN_P,self.E,self.P,self.H,self.mu0)
  self.assertAlmostEqual(x,947.105593777567,places=9)
 def test_native_BPS_upper_source_still_preferred(self):
  x=F.cold_mu(self.pts[-1,1],self.E,self.P,self.H,self.mu0)
  m=(self.pts[-1,2]+self.pts[-1,1])/self.pts[-1,0]
  self.assertGreater(x-m,.10)
 def test_mu0_recalibration_cannot_fix_upper_overlap(self):
  n,p,e=self.pts.T;b=F.match_bound(F.JOIN_P,n,p,e)
  mjoin=F.cold_mu(F.JOIN_P,self.E,self.P,self.H,self.mu0)
  muup=F.cold_mu(p[-1],self.E,self.P,self.H,self.mu0)
  bup=(e[-1]+p[-1])/n[-1]
  self.assertGreater(muup*b['mu_BPS_at_join_lower_bound_MeV']/mjoin-bup,.20)
 def test_same_p_two_EOS_firstlaw_ratio_not_mass_radius_result(self):
  m1=F.cold_mu(.1,self.E,self.P,self.H,self.mu0)
  m2=F.cold_mu(.2,self.E,self.P,self.H,self.mu0)
  self.assertGreater(m2,m1)
 def test_tampered_eos_fails_source_sha(self):
  from tempfile import TemporaryDirectory
  with TemporaryDirectory() as d:
   p=Path(d)/'f.rns'; p.write_bytes(self.R.read_bytes()+b'#evil\n')
   with self.assertRaisesRegex(ValueError,'SOURCE_DRIFT|BYTES_DRIFT'):F.source_f83(p)
 def test_no_global_stability_promotion(self):
  self.assertIn('NOT_ESTABLISHED',F.analyse(tuple(self.pts.T),(self.E,self.P,self.H,self.n,self.mu0))['physical_original_MPA1_Gibbs_or_complete_inner_crust_EOS'])
  self.assertEqual(F.analyse(tuple(self.pts.T),(self.E,self.P,self.H,self.n,self.mu0))['source_native_XPSI_photon_likelihood'],'NOT_RUN')
 def test_nonmonotone_native_bps_fails(self):
  with self.assertRaisesRegex(ValueError,'MONOTONIC'):F.match_bound(F.JOIN_P,*[np.array(x) for x in ([.02,.01,.03],[.05,.08,.4],[25,26,60])])

if __name__=='__main__':unittest.main()
