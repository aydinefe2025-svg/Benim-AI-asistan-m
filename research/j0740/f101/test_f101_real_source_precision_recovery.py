"""Preflight tests use REAL immutable old F100 24 stars, not fabricated stars."""
import os,hashlib,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f101_rescue_only_failed_C_precision import source_report_checks,sha,EXPECTED_ORIGINAL_F100_SHA,EOS_SHA,FAILS,combine
from f101_patch_C_Ridder_Spin_precision_only import patch,OLD,NEW

class F101OriginalImmutableEvidence(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  p=Path(os.environ['F101_ORIGINAL_F100_REPORT'])
  assert sha(p)==EXPECTED_ORIGINAL_F100_SHA
  cls.old=json.loads(p.read_text())
 def test_genuine_source_24_stars_and_399_calls(self):self.assertTrue(source_report_checks(self.old))
 def test_keep_all_four_original_root_failures(self):
  for g,ff in FAILS.items():
   self.assertEqual({x['source_point_index'] for x in self.old['two_grid_results'][g]['real_C_errors']},set(ff))
   self.assertTrue(all(x['error']=="RuntimeError('MEASURED_C_J_MISMATCH')" for x in self.old['two_grid_results'][g]['real_C_errors']))
 def test_real_J_tolerance_not_relaxed(self):
  for entry in self.old['two_grid_results'].values():
   self.assertTrue(all(v['J_relative_error']<=3e-5 for v in entry['actual_C_stars']))
 def test_exact_original_EOS(self):self.assertEqual(self.old['derived_F99_eos_sha256'],EOS_SHA)
 def test_densities_exactly_four_original_missing(self):
  rho=self.old['predeclared_central_densities_g_cm3']
  self.assertEqual(len(rho),14)
  for grid,fs in FAILS.items():
   self.assertEqual([rho[i] for i in fs],[e['rho_g_cm3'] for e in self.old['two_grid_results'][grid]['real_C_errors']])
 def test_original_not_a_dynamic_mode(self):
  self.assertEqual(self.old['real_rotating_dynamical_mode_eigenfrequencies'],'NOT_RUN')
  self.assertEqual(self.old['original_7_EOS_native_MR_photon_evidence'],'NOT_RUN')
 def test_source_patch_is_exactly_reversible(self):
  src='float ans, fh,fl,fm,fnew,sroot,xh,xl,xm,xnew,xacc=1e-5;'
  s='int SetSpin( EOS *eos, NeutronStar *star,\n'+src+'\nint SetJ('
  self.assertEqual(patch(s).replace(NEW,OLD),s)
 def test_duplicated_signature_forbidden(self):
  s='int SetSpin( EOS *eos, NeutronStar *star,\n'+OLD+OLD+'\nint SetJ('
  with self.assertRaises(AssertionError):patch(s)
 def test_require_four_true_new_C_before_combine(self):
  with self.assertRaises(ValueError):combine(self.old,{'151x301':[],'201x401':[]},{'151x301':0,'201x401':0},{})
 def test_no_old_source_mutation(self):
  self.assertEqual(self.old['status'],'REAL_C_PARTIAL_NOT_PHYSICS_ACCEPTED')
  self.assertEqual(self.old['native_real_C_stars'],24)

if __name__=='__main__':unittest.main()
