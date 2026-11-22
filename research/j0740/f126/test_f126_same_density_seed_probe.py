import sys,unittest,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f126_same_density_seed_probe import preflight,parse,classify,sha,STRICT_J_REL
BASE=Path(__file__).resolve().parent
SRC=Path(os.environ['F124_ARTIFACT_ZIP'])
EOS=Path(os.environ['F99_EOS_PATH'])

class NativeSeedTest(unittest.TestCase):
 def test_real_chain(self):
  x=preflight(SRC.read_bytes(),EOS.read_bytes());self.assertLess(x['J_relative_error'],STRICT_J_REL)
 def test_eos_corruption_fails_closed(self):
  with self.assertRaisesRegex(ValueError,'F99_EOS_DIGEST_CHANGED'):preflight(SRC.read_bytes(),EOS.read_bytes()+b'x')
 def test_original_corruption_fails_closed(self):
  with self.assertRaisesRegex(ValueError,'F124_ZIP_DIGEST_CHANGED'):preflight(SRC.read_bytes()+b'x',EOS.read_bytes())
 def test_low_seed_off_target_inconclusive(self):
  h=preflight(SRC.read_bytes(),EOS.read_bytes())
  self.assertEqual(classify({'J_relative_error':1e-5,'M_msun':h['M_msun']-.001},h),'OFF_TARGET_J_SINGLE_LOW_SEED_INCONCLUSIVE')
 def test_low_seed_second_candidate_is_only_candidate(self):
  h=preflight(SRC.read_bytes(),EOS.read_bytes())
  self.assertEqual(classify({'J_relative_error':1e-11,'M_msun':h['M_msun']-.001},h),'TWO_DISTINCT_J_MATCHED_NUMERICAL_CANDIDATES_UNCERTIFIED')
 def test_fake_native_c_stable_format(self):
  out='some header\n2.622286765625e+00 2.1841 1.014e+01 3.454e+02 4.824562679575e+48\n'
  x=parse(out);self.assertEqual(x['rho_g_cm3'],2622286765625000)
if __name__=='__main__':unittest.main(verbosity=2)
