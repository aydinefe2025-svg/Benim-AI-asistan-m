import hashlib
import os
import unittest
import zipfile
from pathlib import Path
from f127_replay_from_real_artifact import (
 F127_ZIP_SHA, F99_EOS_SHA, parse_trace, parse_stdout,replay,
)

F127=Path(os.environ.get('F127_ARTIFACT_ZIP','/mnt/data/F127_fail_closed_original_14776630826.zip'))
EOS=Path(os.environ.get('F99_EOS_PATH','/mnt/data/j0740_f119_source/F99_DERIVED_1981_node_causal_cold_affine_EOS.rns'))

class TestRealF127Replay(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.raw=F127.read_bytes();cls.eos=EOS.read_bytes()

 def test_01_authentic_source_and_cached_stars(self):
  self.assertEqual(hashlib.sha256(self.raw).hexdigest(),F127_ZIP_SHA)
  self.assertEqual(hashlib.sha256(self.eos).hexdigest(),F99_EOS_SHA)
  r=replay(self.raw,self.eos)
  self.assertTrue(r['baseline_original_F124_equivalent_to_initialized_A_at_print_precision'])
  self.assertEqual(r['variants']['a_check_initialized']['spin_trace']['final_rotating_star']['spin_iterations'],9)
  self.assertEqual(r['variants']['a_check_initialized_accuracy_1e7']['spin_trace']['final_rotating_star']['spin_iterations'],32)
  self.assertTrue(0.00063<r['observed']['B_minus_A_mass_Msun']<0.00065)
  self.assertGreater(r['observed']['AB_mass_difference_to_previous_sample_jump_ratio'],16)

 def test_02_corrupt_zip_rejected(self):
  b=bytearray(self.raw);b[100]^=1
  with self.assertRaisesRegex(ValueError,'SHA256_MISMATCH'):replay(bytes(b),self.eos)

 def test_03_corrupt_EOS_rejected(self):
  b=bytearray(self.eos);b[30]^=1
  with self.assertRaisesRegex(ValueError,'SHA256_MISMATCH'):replay(self.raw,bytes(b))

 def test_04_real_multisequence_spin_traces(self):
  with zipfile.ZipFile(F127) as z:
   for name,accuracy,count in [('a_check_initialized',1e-4,11),('a_check_initialized_accuracy_1e7',1e-7,47)]:
    s=z.read('F127/F127_SOURCE_AB_COMPARISON_'+name+'.stderr.txt').decode()
    x=parse_trace(s,accuracy)
    self.assertEqual(x['total_diagnostic_rows'],count)
    self.assertEqual(len(x['calls']),2)
    self.assertLessEqual(x['final_rotating_star']['terminal_dif'],accuracy)

 def test_05_unconverged_last_iteration_rejected(self):
  raw='F127_SPIN_FINAL_DIFFERENCE 1e-4 ITERATIONS 1 ACCURACY 1e-7 ACHECK 0\n'+\
      'F127_SPIN_FINAL_DIFFERENCE 1e-8 ITERATIONS 2 ACCURACY 1e-7 ACHECK 0\n'+\
      'F127_SPIN_FINAL_DIFFERENCE 1e-3 ITERATIONS 1 ACCURACY 1e-7 ACHECK 0\n'+\
      'F127_SPIN_FINAL_DIFFERENCE 1e-4 ITERATIONS 2 ACCURACY 1e-7 ACHECK 0\n'
  with self.assertRaisesRegex(ValueError,'UNCONVERGED'):parse_trace(raw,1e-7)

 def test_06_corrupted_diagnostic_rejected(self):
  raw='F127_SPIN_FINAL_DIFFERENCE 1e-9 ITERATIONS BAD ACCURACY 1e-7 ACHECK 0'
  with self.assertRaisesRegex(ValueError,'MALFORMED'):parse_trace(raw,1e-7)

 def test_07_incomplete_diagnostic_sequence_rejected(self):
  raw='\n'.join(f'F127_SPIN_FINAL_DIFFERENCE 1e-8 ITERATIONS {i} ACCURACY 1e-7 ACHECK 0' for i in [1,2,1,3])
  with self.assertRaisesRegex(ValueError,'INCOMPLETE'):parse_trace(raw,1e-7)

 def test_08_duplicate_stdout_star_rejected(self):
  star='2.622286765625e+00 2.184227160747e+00 1.014016291537e+01 3.454072767354e+02 4.824562676689e+48'
  with self.assertRaisesRegex(ValueError,'EXPECTED_ONE'):parse_stdout(star+'\n'+star)

 def test_09_false_ACHECK_rejected(self):
  raw='\n'.join([f'F127_SPIN_FINAL_DIFFERENCE 1e-8 ITERATIONS {i} ACCURACY 1e-7 ACHECK 0' for i in (1,2)]+[f'F127_SPIN_FINAL_DIFFERENCE 1e-8 ITERATIONS {i} ACCURACY 1e-7 ACHECK 200' for i in (1,2)])
  with self.assertRaisesRegex(ValueError,'INVALID_INNER'):parse_trace(raw,1e-7)

if __name__=='__main__':unittest.main(verbosity=2)
