import sys,unittest,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from replay_f131_original_C import replay_original_real_C, ORIGINAL_F131_SHA
from f131_field_residual import sha

SRC=Path(os.environ['F131_ORIGINAL_FAILED_C_ARTIFACT'])

class OriginalCReplayTests(unittest.TestCase):
 def test_01_genuine_two_native_stars_recovered(self):
    b=SRC.read_bytes();self.assertEqual(sha(b),ORIGINAL_F131_SHA)
    r=replay_original_real_C(b)
    self.assertEqual(r['status'],'TWO_ORIGINAL_REAL_RNS_C_STARS_VALIDATED_NO_NEW_NATIVE_CALL')
    self.assertEqual(set(r['stars']),{'low','high'})
    for label in ('low','high'):
     star=r['stars'][label]['star'];q=star['metric_green_fixedpoint_residual']
     self.assertLess(abs(star['signed_relative_J_residual']),1e-9)
     self.assertLess(star['inner_last_dif'],1e-9)
     self.assertGreater(q['last']['rel_delta_gama'],star['inner_last_dif'])
     self.assertGreater(q['spin_calls'][0]['delta_gama'],0)
     self.assertIsNone(q['spin_calls'][0]['rel_delta_omega'])
 def test_02_pinned_original_sha_rejects_append(self):
    with self.assertRaisesRegex(ValueError,'F131_ORIGINAL_C_SHA_DRIFT'):
      replay_original_real_C(SRC.read_bytes()+b'forgery')
 def test_03_each_observed_absolute_star_matches_previous_F129(self):
    r=replay_original_real_C(SRC.read_bytes())
    for label in ('low','high'):
     st=r['stars'][label]['star'];self.assertAlmostEqual(st['M_baryonic_msun'],2.64712656,places=6)
 def test_04_fixed_point_same_density_scaled_maxima_are_finite(self):
    r=replay_original_real_C(SRC.read_bytes())
    for o in r['stars'].values():
     t=o['star']['metric_green_fixedpoint_residual']['last']
     for name in ('rho','gama','omega'):
      self.assertGreater(t['scale_'+name],0)
      self.assertGreater(t['rel_delta_'+name],0)

if __name__=='__main__':unittest.main()
