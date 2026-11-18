"""F43 independent deterministic tests; not a 7-EOS observational inference."""
import io,json,unittest,zipfile
from pathlib import Path
import numpy as np
from f43_tov_screen import TabEOS,run,sha,EXPECTED_F42_ZIP_SHA

ROOT=Path(__file__).resolve().parent
ARCHIVE=ROOT.parent/'J0740_F42_real_7EOS_candidates_20261118.zip'
RESULT=ROOT/'F43_candidate_tov_results.json'

class F43Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.report=json.loads(RESULT.read_text()); cls.z=zipfile.ZipFile(ARCHIVE)
  cls.f42=json.loads(cls.z.read('F42_candidate_build_report.json'))
  cls.models={}
  for k,v in cls.f42['results'].items():
   cls.models[k]=TabEOS(np.loadtxt(io.BytesIO(cls.z.read(v['new_model_label']+'.rns')),skiprows=1))
 @classmethod
 def tearDownClass(cls):cls.z.close()
 def test_real_source_hash_pin(self):self.assertEqual(sha(ARCHIVE),EXPECTED_F42_ZIP_SHA)
 def test_all_seven_source_models(self):self.assertEqual(set(self.models),{'APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2'})
 def test_original_input_source_kept_separate(self):
  for k,v in self.f42['results'].items():self.assertNotEqual(v['new_model_label'],k)
 def test_causal_interval_speed(self):
  for k,m in self.models.items():
   self.assertGreater(np.min(m.cs2),0,k);self.assertLessEqual(np.max(m.cs2),.990000001,k)
 def test_h_enthalpy_first_law_inversion(self):
  for k,m in self.models.items():
   for h in np.linspace(m.hknots[0],m.hknots[-2],21):
    p,e=m.state(float(h));i=int(np.clip(np.searchsorted(m.p,p,side='right')-1,0,len(m.p)-2))
    self.assertLess(abs(e-(m.e[i]+m.slope[i]*(p-m.p[i]))),max(abs(e)*1e-9,1e-19),k)
 def test_analytic_low_pressure_surface(self):
  for k,m in self.models.items():
   self.assertEqual(m.state(0.),(0.,0.)); p,e=m.state(m.hmin/2);self.assertGreater(p,0);self.assertGreater(e,0)
 def test_2p073_static_branch_root(self):
  for k,v in self.report['eos'].items():
   self.assertTrue(v['candidate_supports_2p073_sampled_static'],k)
   s=v['first_stable_2p073_root'];self.assertIsInstance(s,dict,k)
   self.assertLess(abs(s['fine']['mass_msun']-2.073),1e-6,k)
   self.assertTrue(9<s['fine']['radius_km']<16,k)
 def test_independent_gr_solver_agreement(self):
  for k,v in self.report['eos'].items():
   s=v['first_stable_2p073_root']
   self.assertLess(abs(s['coarse_minus_fine_radius_m']),1,k)
   self.assertLess(abs(s['coarse_minus_fine_mass_msun']),1e-4,k)
 def test_mpa1_max_not_overstated(self):self.assertEqual(self.report['eos']['MPA1']['max_mass_refinement'],'NOT_ESTABLISHED')
 def test_no_final_bayes_or_rotating_gr(self):
  self.assertEqual(self.report['seven_EOS_Bayes'],'NOT_RUN');self.assertEqual(self.report['rotating_GR_stability'],'NOT_RUN')
  self.assertEqual(self.report['physical_model_acceptance'],'NOT_ESTABLISHED')
 def test_reject_corrupt_eos(self):
  tab=np.loadtxt(io.BytesIO(self.z.read(self.f42['results']['ENG']['new_model_label']+'.rns')),skiprows=1)
  tab[4,1]=tab[3,1]
  with self.assertRaises(ValueError):TabEOS(tab)
 def test_reject_wrong_sha(self):
  from unittest.mock import patch
  with patch('f43_tov_screen.EXPECTED_F42_ZIP_SHA','0'*64):
   with self.assertRaises(ValueError):run(ARCHIVE,ROOT/'reject_test_should_not_exist.json')

if __name__=='__main__':unittest.main(verbosity=2)
