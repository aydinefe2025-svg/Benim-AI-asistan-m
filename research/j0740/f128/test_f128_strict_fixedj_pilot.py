import sys,os,io,json,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f128_strict_fixedj_pilot import choose_bracket,load_pinned_source,parse_native,patch_small_mesh,solve_fixed_j,F806_SHA,EOS_SHA,J_TARGET

class F128StrictRealCScientificGateTests(unittest.TestCase):
 def test_01_sign_changing_bracket_uses_nearest_sampled_pair(self):
  s=[{'r_ratio_cli':0.99,'status':'SUCCESS','star':{'signed_J_relative_error':0.1}},
     {'r_ratio_cli':0.992,'status':'SUCCESS','star':{'signed_J_relative_error':-0.1}},
     {'r_ratio_cli':0.991,'status':'SUCCESS','star':{'signed_J_relative_error':-0.02}}]
  b=choose_bracket(s)
  self.assertEqual([x['r_ratio_cli'] for x in b],[0.99,0.991])
 def test_02_nonbracket_returns_none_not_fake_success(self):
  s=[{'r_ratio_cli':0.99,'status':'SUCCESS','star':{'signed_J_relative_error':0.1}},
     {'r_ratio_cli':0.991,'status':'SUCCESS','star':{'signed_J_relative_error':0.05}}]
  self.assertIsNone(choose_bracket(s))
 def test_03_real_immutable_F806_source_hash_and_native_root(self):
  r=load_pinned_source(Path(os.environ['F806_ARTIFACT_ZIP']).read_bytes(),Path(os.environ['F99_EOS_PATH']).read_bytes())
  self.assertEqual(r['source_F806_sha256'],F806_SHA)
  self.assertLess(r['source_root']['J_relative_error'],1e-9)
 def test_04_mutated_real_F806_rejected(self):
  with self.assertRaisesRegex(ValueError,'F806_SOURCE_SHA_MISMATCH'):
   load_pinned_source(Path(os.environ['F806_ARTIFACT_ZIP']).read_bytes()+b'x',Path(os.environ['F99_EOS_PATH']).read_bytes())
 def test_05_mutated_actual_EOS_rejected(self):
  with self.assertRaisesRegex(ValueError,'F99_DERIVED_EOS_SHA_MISMATCH'):
   load_pinned_source(Path(os.environ['F806_ARTIFACT_ZIP']).read_bytes(),Path(os.environ['F99_EOS_PATH']).read_bytes()+b'x')
 def test_06_native_C_honors_true_terminal_iteration_not_one_line(self):
  s='2.6222867578125e+00 2.18425e+00 1.014e+01 3.45e+02 4.8245626795750385e+48\n'
  d='F127_SPIN_FINAL_DIFFERENCE 3e-5 ITERATIONS 7 ACCURACY 1e-7 ACHECK 0\nF127_SPIN_FINAL_DIFFERENCE 6e-8 ITERATIONS 34 ACCURACY 1e-7 ACHECK 0\n'
  r=parse_native(s,d,2622286757812500,0.9902)
  self.assertEqual(r['spin_last_iteration'],34)
  self.assertEqual(r['spin_calls_recorded'],2)
  self.assertLess(r['J_relative_error'],1e-9)
 def test_07_nonnative_duplicate_root_rejected(self):
  s='2.6222867578125e+00 2.18425e+00 1.014e+01 345 4.8245626795750385e+48\n'
  d='F127_SPIN_FINAL_DIFFERENCE 6e-8 ITERATIONS 30 ACCURACY 1e-7 ACHECK 0\n'
  with self.assertRaisesRegex(ValueError,'NOT_ONE_REAL_NATIVE_C_STAR'):parse_native(s+s,d,2622286757812500,0.9902)
 def test_08_old_stopping_tolerance_rejected(self):
  s='2.6222867578125e+00 2.18425e+00 1.014e+01 345 4.8245626795750385e+48\n'
  d='F127_SPIN_FINAL_DIFFERENCE 8e-5 ITERATIONS 9 ACCURACY 1e-4 ACHECK 0\n'
  with self.assertRaisesRegex(ValueError,'RNS_INNER_STOP_NOT_CONVERGED_TO_STRICT_TOLERANCE'):parse_native(s,d,2622286757812500,0.9902)
 def test_09_makefile_source_patch_guards_mesh(self):
  self.assertIn('MDIV=601 -DSDIV=1201',patch_small_mesh('HIGHSIZE=-DMDIV=151 -DSDIV=301'))
  with self.assertRaisesRegex(ValueError,'PINNED_MAKEFILE_MESH_SOURCE_DRIFT'):
   patch_small_mesh('HIGHSIZE=-DMDIV=601 -DSDIV=1201')

 def test_10_synthetic_root_algorithm_accepts_only_matching_J(self):
  class FakeNativeProbe:
   def __init__(self):self.cache={}
   def evaluate(self,ratio):
    ratio=float(f'{ratio:.12f}');key=f'{ratio:.12f}'
    if key not in self.cache:
     signed=(0.990217000000-ratio)*50.0
     self.cache[key]={'status':'SUCCESS','r_ratio_cli':ratio,
                      'star':{'signed_J_relative_error':signed,'J_relative_error':abs(signed),'r_ratio':ratio}}
    return self.cache[key]
  x=FakeNativeProbe();r=solve_fixed_j(x)
  self.assertEqual(r['status'],'ACCEPTED_STRICT_SAME_J_ROOT')
  self.assertLessEqual(r['star']['J_relative_error'],1e-9)
  self.assertTrue(all(row['status']=='SUCCESS' for row in x.cache.values()))
 def test_11_synthetic_root_algorithm_cannot_claim_success_without_J_sign_change(self):
  class FakeNativeProbe:
   def __init__(self):self.cache={}
   def evaluate(self,ratio):
    key=f'{ratio:.12f}'
    self.cache[key]={'status':'SUCCESS','r_ratio_cli':float(key),
                     'star':{'signed_J_relative_error':0.01,'J_relative_error':0.01}}
    return self.cache[key]
  r=solve_fixed_j(FakeNativeProbe())
  self.assertEqual(r['status'],'INCONCLUSIVE_NO_SIGN_CHANGE')

if __name__=='__main__':unittest.main(verbosity=2)
