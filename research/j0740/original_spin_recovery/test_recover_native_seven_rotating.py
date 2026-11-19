"""Adversarial unit and authentic evidence tests against source-fixed GitHub C stars."""
import unittest,copy,json,tempfile,base64
from pathlib import Path
import recover_native_seven_rotating as r

HERE=Path(__file__).resolve().parent
class NativeSevenRecoveredSourceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.d,cls.source,cls.manifest=r.load_all(HERE)
 def test_true_seven_source_original_models_7_of_7(self):
  self.assertEqual(set(self.d),set(r.SEVEN))
  self.assertEqual(sum(x['raw_original_solver_count'] for x in self.d.values()),323)
  self.assertEqual([self.d[n]['raw_original_solver_count'] for n in ('WFF1','WFF2')],[41,42])
 def test_wff_did_cross_2p073_and_witness_postpeak(self):
  for model in ('WFF1','WFF2'):
   v=self.d[model]
   self.assertGreaterEqual(v['observed_after_peak_count'],2)
   self.assertGreater(v['highest_density_mass_drop_below_peak_msun'],.003)
   self.assertLess(abs(v['massline_vs_exact_C_target_R_delta_m']),.25)
 def test_original_physics_is_not_tampered_and_not_certified(self):
  for label,v in self.d.items():
   self.assertEqual(v['physical_EOS_global_admissibility'],'NOT_ESTABLISHED')
   self.assertEqual(v['continuous_constant_J_stability'],'NOT_ESTABLISHED')
   self.assertLess(v['accepted_numeric_source_mass_range_msun'][0],2.073)
   self.assertGreater(v['accepted_numeric_source_mass_range_msun'][1],2.073)
 def test_crash_resumption_requires_real_late_C_timeout(self):
  obj=copy.deepcopy(self.source['WFF1']);obj['failing_gate']['type']='ValueError'
  with self.assertRaisesRegex(r.EvidenceFailure,'not the original'):
   r.valid_direct_C_branch('WFF1',obj)
 def test_fails_if_nonphysical_early_peak_without_sampled_decrease(self):
  obj=copy.deepcopy(self.source['WFF2']);obj['raw_C_rotating_stars'][-1]['mass_msun']=obj['raw_C_rotating_stars'][-3]['mass_msun']+.01
  with self.assertRaises(r.EvidenceFailure):r.valid_direct_C_branch('WFF2',obj)
 def test_fails_wrong_spin_source_C_output(self):
  obj=copy.deepcopy(self.source['ENG']);obj['raw_C_rotating_stars'][3]['spin_hz_reported']+=1
  with self.assertRaisesRegex(r.EvidenceFailure,'physics mismatched'):
   r.valid_direct_C_branch('ENG',obj)
 def test_cannot_relabel_missing_source_as_success(self):
  obj=copy.deepcopy(self.source['WFF1']);obj['raw_C_rotating_stars']=obj['raw_C_rotating_stars'][:5]
  with self.assertRaisesRegex(r.EvidenceFailure,'count changed'):
   r.valid_direct_C_branch('WFF1',obj)
 def test_reject_hash_modified_original_GitHub_artifact(self):
  from shutil import copytree
  with tempfile.TemporaryDirectory() as td:
   folder=Path(td)
   (folder/'artifacts').mkdir()
   name=self.manifest['artifacts']['WFF1']['file'];src=HERE/'artifacts'/name
   (folder/'artifacts'/name).write_text(src.read_text()[:-2]+'A\n')
   with self.assertRaises(r.EvidenceFailure):r.load_archived_original(folder/'artifacts','WFF1',self.manifest)
 def test_WFF_prior_coverage_narrower_than_other_seven(self):
  self.assertTrue(.80<self.d['WFF1']['source_radio_mass_prior_covered_fraction']<.82)
  self.assertTrue(.96<self.d['WFF2']['source_radio_mass_prior_covered_fraction']<.97)
  self.assertTrue(.99<self.d['MPA1']['source_radio_mass_prior_covered_fraction']<=1.000001)
 def test_source_input_manifest_seven_ZIPs_byte_pinned(self):
  for name in r.SEVEN:
   self.assertEqual(self.source[name]['source_original_npz_sha256'],r.SEVEN[name])
   self.assertEqual(len(self.manifest['artifacts'][name]['zip_sha256']),64)
if __name__=='__main__':unittest.main()
