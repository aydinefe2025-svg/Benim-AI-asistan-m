"""F90 independent receipt tests; real NPZ/JSONL are held privately on Windows, not mocked by CI."""
import hashlib,json,math,unittest
from pathlib import Path
P=Path(__file__).with_name('F90_real_source_8192_replay_20261121.json')
PIN='3c8d25ada8c148c961187ce18a78575c2c178f1160f3c69bb13614172a9baf53'
SOURCE='049a1ac945b09af595d282d958842cd95475e509d6b7e79b45c72d11096de227'
class F90ReceiptCrossAudit(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.o=json.loads(P.read_text())
 def test_genuine_pinned_manifest_and_source(self):
  a=self.o;self.assertEqual(a['source_manifest_sha256'],PIN)
  self.assertEqual(a['original_source_model_sha256'],SOURCE)
  self.assertEqual(a['previous_native_calls'],10817)
  self.assertEqual(a['new_photon_likelihood_calls'],0)
 def test_four_untampered_distinct_file_hashes(self):
  x=self.o['seeds'];self.assertEqual(len(x),4)
  self.assertEqual({r['seed'] for r in x},{198301,198303,198307,198311})
  self.assertEqual(len({r['npz_sha256'] for r in x}),4)
  self.assertEqual(len({r['jsonl_sha256'] for r in x}),4)
  for r in x:
   self.assertEqual(r['draws'],2048)
   for key in ('npz_sha256','jsonl_sha256'):
    self.assertEqual(len(r[key]),64)
    int(r[key],16)
 def test_raw_reconstruction_numerical_precision(self):
  for r in self.o['seeds']:
   self.assertLess(r['max_abs_recomputed_logweight_difference'],1e-10)
   self.assertLess(r['source_phase_delta_max'],1e-7)
   self.assertLessEqual(r['max_weight_fraction'],1)
 def test_original_fail_not_rebranded_as_pass(self):
  a=self.o;self.assertEqual(a['overall_fixed_original_four_seed_acceptance'],'FAIL_UNCHANGED')
  self.assertEqual([(x['seed'],x['status']) for x in a['seeds']],[(198301,'FAIL'),(198303,'PASS'),(198307,'PASS'),(198311,'PASS')])
  self.assertGreater(a['seeds'][0]['max_weight_fraction'],.02)
  self.assertTrue(a['source_198301_FAIL_unmodified'])
 def test_pooled_ess_independent_formula(self):
  a=self.o;x=a['seeds'];v=[s['recomputed_logI'] for s in x]
  top=max(v);s=sum(math.exp(t-top) for t in v)
  p=[math.exp(t-top)/s for t in v]
  eff=1/sum(p[i]**2/x[i]['ESS'] for i in range(4))
  self.assertAlmostEqual(eff,a['pooled_diagnostic_not_per_seed_acceptance']['ESS'],places=8)
  self.assertAlmostEqual(top+math.log(s)-math.log(4),a['pooled_diagnostic_not_per_seed_acceptance']['logI'],places=9)
 def test_pooled_max_weight_and_source_support_math(self):
  a=self.o;x=a['seeds'];v=[s['recomputed_logI'] for s in x]
  top=max(v);weights=[math.exp(y-top) for y in v];z=sum(weights)
  maxw=max(weights[i]/z*x[i]['max_weight_fraction'] for i in range(4))
  self.assertAlmostEqual(maxw,a['pooled_diagnostic_not_per_seed_acceptance']['max_weight'],places=14)
  self.assertAlmostEqual(-math.log(a['original_support_factor']),a['log_support_correction'],places=12)
  self.assertEqual(a['final_full_MR_photon_Bayes'],'NOT_RUN')
if __name__=='__main__':unittest.main()
