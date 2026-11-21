#!/usr/bin/env python3
"""F94: independent algorithm/source receipt gates. Offline CI never pretends to have private NPZ/JSONL."""
import hashlib,json,math,statistics,unittest
from pathlib import Path
R=Path(__file__).resolve().parent
def source(name):return json.loads((R/name).read_text(encoding='utf-8-sig'))
def sha(name):return hashlib.sha256((R/name).read_bytes()).hexdigest()
FILE='F94_source_F91_v2_four_seed_NATIVE_FAIL_20261121.json'
REPLAY='F94_independent_source_F91_v2_NATIVE_FAIL_replay_20261121.json'
INTEGRAL='F94_real_two_stage_importance_4096_20261121.json'
class RealSourceF94(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.f=source(FILE);cls.r=source(REPLAY);cls.e=source(INTEGRAL)
 def test_exact_real_native_run_sha(self):
  self.assertEqual(sha(FILE),'656d6137ec85a4bc5241c3ca6c2aa1aeca8ac215363e4d56b8b647cf2431b2b1')
  self.assertEqual(sha(REPLAY),'35172eaf016fdbf5c9bbd3ac1affe62ed4979639d6da87641d7aa998c951d7c3')
  self.assertEqual(sha(INTEGRAL),'e0b7a98b793406739fe7cf166989ff263e137243e53e57b0c7c6c09941d0f60d')
 def test_native_1851_real_calls_and_no_fake_success(self):
  a=self.f
  self.assertEqual(a['status'],'FAIL_FRESH_NATIVE_SAMPLER_NOT_ACCEPTED')
  self.assertEqual(a['new_native_photon_likelihood_calls'],1851)
  self.assertEqual(sum(x['new_photon_calls'] for x in a['runs']),1851)
  self.assertEqual(a['new_independent_seeds'],[211401,211403,211407,211411])
  self.assertEqual(a['target'],[2.073,15.26])
  self.assertEqual(a['EOS_Bayes'],'NOT_RUN')
  self.assertEqual(a['full_MR_coverage'],'NOT_DONE')
 def test_fail_gate_not_relaxed(self):
  a=self.f
  self.assertEqual(a['acceptance_thresholds'],{'ESS_min_each':100,'maxW_max_each':.05,'phase_ESS_min_each':30,
    'half_256_512_logI_drift_max_each':.1,'between_seed_logI_range_max':.2})
  self.assertTrue(all(not k for k in a['original_prespecified_gates'].values()))
 def test_independent_all_four_samples_against_native(self):
  a,b=self.f,self.r
  self.assertEqual(b['status'],'FOUR_FRESH_NATIVE_SEEDS_VERIFIED_FAIL')
  self.assertFalse(b['accepted'])
  self.assertEqual(b['pending_seeds'],[])
  self.assertEqual(b['partial_seeds'],[])
  self.assertEqual(b['model_source_evaluations_run_by_this_audit'],0)
  self.assertEqual(b['physical_source_model_sha256'],a['source_likelihood_model_sha256'])
  self.assertEqual(b['frozen_design_sha256'],a['frozen_design_sha256'])
  for x,y in zip(a['runs'],b['seed_results']):
   self.assertEqual(x['seed'],y['seed'])
   self.assertEqual(x['source_npz_sha256'],y['npz_sha256'])
   self.assertEqual(x['original_raw_jsonl_sha256'],y['source_jsonl_sha256'])
   self.assertEqual(x['new_photon_calls'],y['new_native_photon_calls_preserved'])
   self.assertAlmostEqual(x['diagnostics']['ESS'],y['ESS'],places=6)
   self.assertAlmostEqual(x['diagnostics']['max_weight_fraction'],y['max_weight_fraction'],places=9)
   self.assertLess(y['max_reconstructed_abs_logweight_error'],1e-9)
 def test_v2_fail_two_seed_witness(self):
  a=self.r['seed_results']
  self.assertEqual([x['independently_passed_per_seed'] for x in a],[True,False,True,False])
  self.assertLess(a[1]['ESS'],30)
  self.assertGreater(a[1]['max_weight_fraction'],.18)
  self.assertLess(a[3]['ESS'],100)
  self.assertGreater(a[3]['max_weight_fraction'],.08)
 def test_two_stages_both_still_fail_original_acceptance(self):
  e=self.e
  self.assertEqual(e['original_independent_seed_acceptance'],{'V1':'FAIL','V2':'FAIL'})
  self.assertEqual(e['total_real_native_photon_model_draws_reused'],4096)
  self.assertEqual(e['new_native_photon_calls'],0)
  self.assertEqual(e['full_MR_EOS_Bayes'],'NOT_RUN')
  self.assertEqual(e['target'],[2.073,15.26])
 def test_each_stage_logI_recomputed_from_four_seed_integrals(self):
  for stage in self.e['stages']:
   self.assertEqual(stage['draws'],2048)
   v=[r['logI'] for r in stage['seed_reports']]
   self.assertEqual(len(v),4)
   c=max(v)
   out=c+math.log(sum(math.exp(k-c) for k in v)/4)
   self.assertAlmostEqual(out,stage['logI_stage'],places=9)
   q=[math.exp(k-out) for k in v]
   se=statistics.stdev(q)/math.sqrt(4)
   self.assertAlmostEqual(se,stage['relative_standard_error_from_four_scrambled_QMC_replicates'],places=9)
   self.assertAlmostEqual(max(v)-min(v),stage['max_replicate_logI_minus_min'],places=9)
 def test_correct_adaptive_sequential_combination(self):
  e=self.e; x=[t['logI_stage'] for t in e['stages']]; m=max(x)
  avg=sum(math.exp(v-m) for v in x)/2
  self.assertAlmostEqual(m+math.log(avg),e['logI_two_stage_point_estimate'],places=9)
  rel=(sum((math.exp(x[i]-m)*e['stages'][i]['relative_standard_error_from_four_scrambled_QMC_replicates'])**2 for i in range(2))**.5)/(2*avg)
  self.assertAlmostEqual(rel,e['estimated_relative_standard_error_RQMC'],places=11)
  self.assertGreater(rel,.02)
 def test_adaptive_mis_is_not_claimed_independently_valid(self):
  e=self.e
  self.assertIn('Do NOT treat cross-density balance MIS',e['correction'])
  self.assertTrue(e['source_model_physics_changed_between_stages'] is False)
  self.assertTrue(e['combined_max_normalized_weight_diagnostic']>.02)
 def test_portable_sources_syntax_checked_without_photon(self):
  for name in ('f94_independent_F91_v2_raw_photon_replay.py','f94_real_two_stage_importance_from_private_4096.py'):
   compile((R/name).read_text(encoding='utf-8-sig'),name,'exec')
if __name__=='__main__':unittest.main()
