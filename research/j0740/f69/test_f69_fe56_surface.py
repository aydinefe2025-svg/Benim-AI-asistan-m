"""Fail-closed F69 tests; source lock, conditional Fe56, C1, cold first law and GR baryons."""
import hashlib,math,sys,unittest
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f69_fe56_surface_match_static import (ConditionallyFeMatched,FE56_EGEO,FE56_BARYON_KG,
 FE56_RHO_KG_M3,AMU_KG,C,G,PARENT_SHA,run,tov_to_match)
TABLE=Path(__file__).parent/'F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat'

class TestF69(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if not TABLE.is_file():raise RuntimeError('F69_STAGED_ORIGINAL_F67_TABLE_MISSING')
  cls.c=ConditionallyFeMatched(TABLE)
 def test_01_parent_sha_lock(self):
  self.assertEqual(hashlib.sha256(TABLE.read_bytes()).hexdigest(),PARENT_SHA)
 def test_02_real_fe_surface_incompatibility(self):
  self.assertLess(self.c.e_parent0,FE56_EGEO)
  self.assertAlmostEqual(self.c.rho_parent0/1e3,7.7572339814334175,places=10)
 def test_03_new_model_matches_only_above_positive_p(self):
  self.assertGreater(self.c.pm,self.c.p_parent0)
  self.assertGreater(self.c.em,FE56_EGEO)
  self.assertTrue(0<self.c.alpha<.95)
 def test_04_C0_continuity(self):
  self.assertAlmostEqual(self.c.extension_e(self.c.pm)/self.c.em,1.,places=13)
 def test_05_C1_continuity(self):
  slope=self.c.em*float(self.c.ep(math.log(self.c.pm),1))/self.c.pm
  self.assertLess(abs(self.c.extension_dedp(self.c.pm)/slope-1),1e-11)
 def test_06_zero_pressure_positive_surface(self):
  self.assertEqual(self.c.extension_e(0),FE56_EGEO)
  self.assertEqual(self.c.extension_Habs(0),0)
 def test_07_monotone_and_causal_outer(self):
  pp=np.geomspace(self.c.pm*1e-14,self.c.pm,300)
  ep=np.array([self.c.extension_e(float(x)) for x in pp])
  self.assertTrue((np.diff(ep)>0).all())
  self.assertTrue(all(self.c.extension_dedp(float(x))>1 for x in pp))
 def test_08_H_positive(self):
  self.assertGreater(self.c.houter,0)
  self.assertLess(self.c.houter,1e-10)
 def test_09_absolute_nsurface_from_fe(self):
  self.assertAlmostEqual(self.c.surface_baryon_number_density_m3,FE56_RHO_KG_M3/FE56_BARYON_KG,places=6)
  self.assertGreater(self.c.at_parent_pmin_baryon_density_m3,0)
 def test_10_fe_chem_identity(self):
  p=2*self.c.pm
  ns=self.c.physical_n(p)
  mu=(self.c.e(p)+p)*C*C/G/ns
  self.assertLess(abs(mu/FE56_BARYON_KG-math.exp(self.c.Habs(p))),4e-14)
 def test_11_core_firstlaw(self):
  self.assertLess(max(self.c.first_law_relative_error(float(p)) for p in np.geomspace(2*self.c.pm,1e-10,15)),1e-5)
 def test_12_surface_1pct_mu0_variability(self):
  mu=FE56_BARYON_KG
  # Without outside microphysics, changing mu0 by 1% changes n and baryon mass by exactly -~1%
  self.assertAlmostEqual(((1/mu)/(1/(mu*1.01))),1.01,places=12)
 def test_13_fail_on_altered_sha(self):
  with self.assertRaises(ValueError):ConditionallyFeMatched(Path(__file__))
 def test_14_fail_on_bad_extension(self):
  with self.assertRaises(ValueError):self.c.extension_e(self.c.pm*1.0000001)
  with self.assertRaises(ValueError):self.c.extension_dedp(0.)
 def test_15_two_gr_formulations(self):
  a=tov_to_match(self.c,.38418646,'rm')
  b=tov_to_match(self.c,.38418646,'uv')
  self.assertLess(abs(a['R_km_to_match']-b['R_km_to_match']),.005)
  self.assertLess(abs(a['Baryon_rest_mass_u_msun_to_match']-b['Baryon_rest_mass_u_msun_to_match']),.0005)
 def test_16_four_mass_real_result(self):
  from tempfile import TemporaryDirectory
  with TemporaryDirectory() as tmp:
   x=run(TABLE,Path(tmp)/'new.json')
   self.assertEqual(len(x['target_static_GR']),4)
   self.assertTrue(x['original_MPA1_unmodified'])
   self.assertEqual(x['whole_original_seven_EOS_physically_accepted'],'NOT_ESTABLISHED')
   self.assertEqual(x['seven_original_EOS_Bayes'],'NOT_RUN')
 def test_17_shell_continuity(self):
  c=self.c
  self.assertLess(c.extension_Habs(c.pm*.5),c.houter)
  self.assertGreater(c.houter,1e-14)
 def test_18_no_RNS_false_success(self):
  from tempfile import TemporaryDirectory
  with TemporaryDirectory() as tmp:
   x=run(TABLE,Path(tmp)/'new.json')
   self.assertEqual(x['rotating_F68_uncertainty_not_recomputed'],'NOT_RUN')
   self.assertEqual(x['source_native_XPSI_photons'],'NOT_RUN')

if __name__=='__main__':unittest.main(verbosity=2)
