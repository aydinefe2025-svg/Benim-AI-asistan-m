#!/usr/bin/env python3
"""Adversarial fail-closed regressions for real historical failed-seed summary."""
import copy
import importlib.util
import math
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('f85',Path(__file__).with_name('f85_native_heldout_replay.py'))
f85=importlib.util.module_from_spec(spec);spec.loader.exec_module(f85)

BASE={'seed':198301,'sample_identity_rows_pass':2048,'status':'FAIL','kind':'EXACT_2048_DRAW_HELDOUT_FIRST_SEED_FAIL',
'frozen_proposal_sha256':'frozen','max_abs_logweight_reconstruction_difference':0.,
'source_model_sha256':'source','npz_sha256':'npz','jsonl_sha256':'jsonl',
'gates':{'ESS_min_400':True,'maxW_max_0p02':False,'drift_max_0p10':True,'min_phase_ESS_min_100':True},
'independently_reconstructed':{'ESS':430.7264905645419,'max_weight_fraction':0.026068854248150627,'half_full_logI_drift':0.02366082393564284,'min_phase_half_ESS':182.38717212369775,'finite_source_likelihood_count':1721},
'top_samples':[
 {'index':932,'fraction_of_total_normalized_weight':0.026068854248150627,'q_v3_over_q_base':0.5658194546506483,'z2':-.6747732099574584,'z6':-.8990603400489771,'mixture_pdf_component_share':{'base':.8836741046818791,'K4':.10665723777704818,'tail':.009668657541072668}},
 {'index':1900,'fraction_of_total_normalized_weight':0.009420487586637195,'q_v3_over_q_base':1.3168985139228526},
]}
TRAIN={'frozen_proposal_sha256':'frozen','frozen_before_validation':True}

class ActualHeldoutSummary(unittest.TestCase):
 def setUp(self):self.report=copy.deepcopy(BASE);self.train=copy.deepcopy(TRAIN)
 def test_real_source_result_retains_FAIL(self):
  r=f85.audit(self.report,self.train);self.assertEqual(r['real_seed_198301_status'],'FAIL_UNCHANGED');self.assertEqual(r['new_native_XPSI_photon_calls_this_audit'],0)
 def test_top_square_weight_fraction(self):
  r=f85.audit(self.report,self.train);self.assertAlmostEqual(r['top_weight_squared_fraction_of_all_weight_squares'],.29271533178672665,places=9)
 def test_exact_needed_density_factor(self):
  r=f85.audit(self.report,self.train);self.assertAlmostEqual(r['counterfactual_DO_NOT_USE_FOR_SCIENCE']['top_local_q_factor_needed_if_others_fixed'],1.311564851099696)
 def test_no_fabricated_success_after_top_counterfactual(self):
  r=f85.audit(self.report,self.train);self.assertLess(r['counterfactual_DO_NOT_USE_FOR_SCIENCE']['hypothetical_top_weight_if_only_top_q_used_qbase'],.02);self.assertEqual(r['real_seed_198301_status'],'FAIL_UNCHANGED')
 def test_reject_proposal_training_mismatch(self):
  self.train['frozen_proposal_sha256']='different';self.assertRaises(f85.SourceError,f85.audit,self.report,self.train)
 def test_reject_changed_draw_count(self):
  self.report['sample_identity_rows_pass']=1024;self.assertRaises(f85.SourceError,f85.audit,self.report,self.train)
 def test_reject_changed_seed(self):
  self.report['seed']=198303;self.assertRaises(f85.SourceError,f85.audit,self.report,self.train)
 def test_reject_altered_threshold(self):
  self.report['gates']['maxW_max_0p02']=True;self.assertRaises(f85.SourceError,f85.audit,self.report,self.train)
 def test_reject_duplicate_top(self):
  self.report['top_samples'][1]['index']=932;self.assertRaises(f85.SourceError,f85.audit,self.report,self.train)
 def test_reject_unfrozen_proposal(self):
  self.train['frozen_before_validation']=False;self.assertRaises(f85.SourceError,f85.audit,self.report,self.train)
 def test_reject_invalid_pdf_components(self):
  self.report['top_samples'][0]['mixture_pdf_component_share']['base']=.9;self.assertRaises(f85.SourceError,f85.audit,self.report,self.train)
 def test_reject_invalid_ess(self):
  self.report['independently_reconstructed']['ESS']=float('nan');self.assertRaises(f85.SourceError,f85.audit,self.report,self.train)
 def test_sha_git_object(self):self.assertEqual(f85.git_blob_sha(b'hello\n'),'ce013625030ba8dba906f756967f9e9ca394464a')
 def test_raw_missing_file_rejected(self):
  self.assertRaises(FileNotFoundError,f85.raw_replay,Path('/missing/path/hello.npz'),Path('/missing/path/event.jsonl'),self.report)

if __name__=='__main__':unittest.main()
