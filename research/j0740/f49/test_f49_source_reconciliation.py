import unittest,tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
import f49_reconcile_seven_complete_c_gr as f

class Tests(unittest.TestCase):
 def test_source_identity_all_seven(self):
  self.assertEqual(len(f.SIX_SOURCE_SHA),6)
  self.assertEqual(set(f.SIX_SOURCE_SHA)|{'WFF1'},set(f.previous.EOS))
 def test_immutable_F48_source_pin(self):self.assertEqual(len(f.F48_SHA),64)
 def test_reject_corrupted_real_F48_source(self):
  with tempfile.TemporaryDirectory() as d:
   z=Path(d)/'bad.zip';z.write_bytes(b'bad')
   with self.assertRaisesRegex(ValueError,'PINNED_F48_REAL_C_GR_ARTIFACT_SHA_MISMATCH'):
    f.restore_wff1(z,Path(d))
 def test_all_results_are_still_conditional(self):
  self.assertEqual(f.previous.M0,1.95)
  self.assertEqual(f.previous.M1,2.10)
  self.assertEqual(f.previous.F38_SHA,'4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307')
  self.assertAlmostEqual(f.previous.prior_window_probability(),0.5708291253531559,places=12)
 def test_original_7_posterior_not_run(self):
  self.assertEqual(len(f.ORIGINAL_F47_RESULT_SHA),64)
 def test_upstream_f47_receipt_versions_are_both_accepted_only_when_complete(self):
  for version in f.F47_ALLOWED_BACKEND_STATUSES:
   good={'status':version,'missing_direct_RNS_targets':{n:[] for n in f.previous.EOS}}
   self.assertEqual(f.validate_backend_state(good),version)
 def test_upstream_f47_missing_star_fails_closed(self):
  good={'status':next(iter(sorted(f.F47_ALLOWED_BACKEND_STATUSES))),
        'missing_direct_RNS_targets':{n:[] for n in f.previous.EOS}}
  good['missing_direct_RNS_targets']['WFF1']=[2.0175]
  with self.assertRaisesRegex(ValueError,'MISSING_OR_UNEXPECTED_DIRECT'):
   f.validate_backend_state(good)
 def test_unknown_upstream_status_fails_closed(self):
  bad={'status':'untrusted','missing_direct_RNS_targets':{n:[] for n in f.previous.EOS}}
  with self.assertRaisesRegex(ValueError,'UNEXPECTED_F47_BACKEND'):
   f.validate_backend_state(bad)
if __name__=='__main__':unittest.main(verbosity=2)
