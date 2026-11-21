#!/usr/bin/env python3
"""F91 independent permanent receipts, never treat source native 2/4 FAIL as PASS."""
from __future__ import annotations
import hashlib,json,unittest
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent
def data(name):return json.loads((R/name).read_bytes())
def sha(name):return hashlib.sha256((R/name).read_bytes()).hexdigest()
class NativeFrozenEvidenceGates(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.old=data('F91_v1_original_frozen_source_design_20261121.json')
  cls.v1=data('F91_v1_native_four_seed_failure_original_report_20261121.json')
  cls.ind=data('F91_v1_independent_four_seed_raw_replay_failure_20261121.json')
  cls.new=data('F91_v2_frozen_15p26_tail_design_20261121.json')
 def test_exact_original_frozen_source_design_hash(self):
  self.assertEqual(sha('F91_v1_original_frozen_source_design_20261121.json'),'50477db36217448177ef489980b395d6a92f37ec2409f2187b3420a0267bff82')
  self.assertEqual(sha('F91_v1_native_four_seed_failure_original_report_20261121.json'),'920db7671b9f6378d7880d3372d6985e048f64fc07745952a1a67b3fad51a4f4')
 def test_original_status_FAIL_never_patched(self):
  a=self.v1
  self.assertEqual(a['status'],'FAIL')
  self.assertFalse(a['gates']['ESS_per_run_min'])
  self.assertFalse(a['gates']['max_weight_fraction_max'])
  self.assertGreater(a['metrics']['max_weight'],.05)
  self.assertLess(a['metrics']['min_ESS'],100)
  self.assertEqual(a['EOS_Bayes'],'NOT_RUN')
 def test_original_fresh_seeds_consistent_with_immutable_source(self):
  self.assertEqual(self.old['fresh_validation_seeds'],[211301,211303,211307,211311])
  self.assertEqual(self.v1['independent_seeds'],self.old['fresh_validation_seeds'])
  self.assertEqual(self.v1['frozen_design_sha256'],sha('F91_v1_original_frozen_source_design_20261121.json'))
 def test_independent_real_raw_replay_source_and_two_seeds_fail(self):
  x=self.ind
  self.assertEqual(x['status'],'FAIL_SOURCE_CANDIDATE_NOT_ACCEPTED')
  self.assertEqual(x['frozen_design_sha256'],sha('F91_v1_original_frozen_source_design_20261121.json'))
  self.assertEqual(x['num_new_photon_calls_in_this_independent_replay'],0)
  self.assertEqual([i['seed'] for i in x['seeds']],[211301,211303,211307,211311])
  self.assertEqual(x['pending_seeds'],[])
  for row in x['seeds']:
   self.assertLess(row['max_abs_recomputed_weight_diff'],1e-9)
   self.assertLess(row['max_source_QMC_z_abs_diff'],1e-11)
  self.assertFalse(x['seeds'][2]['per_seed_gate']['ESS_ge_100'])
  self.assertFalse(x['seeds'][3]['per_seed_gate']['maxW_le_0p05'])
 def test_new_candidate_original_fail_preserved_and_new_seeds(self):
  x=self.new
  self.assertEqual(x['status'],'FROZEN_NEW_PROPOSAL_NOT_YET_FRESHLY_EVALUATED')
  self.assertEqual(x['historical_original_design_sha256'],sha('F91_v1_original_frozen_source_design_20261121.json'))
  self.assertEqual(x['historical_validation_status_211307'],'FAIL_PER_SEED_ESS_79p49595_MAXW_0p0609704566')
  self.assertEqual(x['NEW_INDEPENDENT_VALIDATION_SEEDS'],[211401,211403,211407,211411])
  self.assertFalse(set(x['NEW_INDEPENDENT_VALIDATION_SEEDS'])&set(self.old['fresh_validation_seeds']))
  self.assertEqual(x['native_photon_calls_in_this_design'],0)
  self.assertFalse(x['data_clipped_or_altered'])
  self.assertEqual(x['EOS_Bayes'],'NOT_RUN')
 def test_original_acceptance_thresholds_not_relaxed(self):
  t=self.new['FIXED_PRIOR_ACCEPTANCE_GATES']
  self.assertEqual(t,dict(ESS_min_each=100,maxW_max_each=.05,phase_ESS_min_each=30,
    half_256_512_logI_drift_max_each=.1,between_seed_logI_range_max=.2))
  self.assertFalse(self.v1['source_prior_or_likelihood_changed'])
 def test_frozen_covariances_are_positive_definite(self):
  x=self.new
  m=np.array(x['centers_in_unit_jacobian_transport_coordinates'],dtype=float)
  c=np.array(x['covariances'],dtype=float)
  self.assertEqual(m.shape,(8,13));self.assertEqual(c.shape,(8,13,13))
  self.assertTrue(np.isfinite(m).all() and np.isfinite(c).all())
  self.assertTrue(np.allclose(c,c.transpose(0,2,1),atol=1e-9))
  self.assertGreater(min(np.linalg.eigvalsh(mat).min() for mat in c),0)
  self.assertEqual(x['epsilon'],.2);self.assertEqual(x['df'],8.0)
 def test_python_source_compiles_with_no_photon_load(self):
  for name in ('f91_independent_real_raw_15p26_verifier.py','f91_v2_native_xpsi_fresh_runner.py',
               'f91_v1_original_source_real_native_runner.py'):
   source=(R/name).read_text(encoding='utf-8-sig')
   compile(source,name,'exec')
 def test_no_full_MR_photon_Bayes_claim(self):
  self.assertEqual(self.ind['claim_eos_full_bayes'],'NOT_RUN')
  self.assertEqual(self.new['original_XPSI_15p26_target_mass_radius'],[2.073,15.26])
  self.assertEqual(self.v1['all_MR_domain_certified'],False)
if __name__=='__main__':unittest.main()
