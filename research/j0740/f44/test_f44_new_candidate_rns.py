import json,unittest,tempfile,io,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import f44_seven_new_candidate_rns as f

class F44Tests(unittest.TestCase):
 def test_source_identity_7(self):self.assertEqual(len(f.EOS),7)
 def test_source_sha_enforced(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'fake.zip';p.write_bytes(b'invalid')
   with self.assertRaisesRegex(ValueError,'F42_SOURCE_SHA_MISMATCH'):f.verify_f42(p,Path(t)/'out')
 def test_parser_valid_geometric_gr(self):
  s='1.78 2.073 10.7 346.536369 1.9\n'
  a=f.parse_rns(s,1.78e15,.985)
  self.assertAlmostEqual(a['mass_msun'],2.073)
  self.assertEqual(a['baryonic_M0'],'NOT_INTERPRETED_SOURCE_CALIBRATION_NOT_CERTIFIED')
 def test_parser_reject_wrong_density(self):
  with self.assertRaisesRegex(ValueError,'wrong center'):f.parse_rns('1.0 2.073 11.1 346.5 2.2',1.5e15,.98)
 def test_parser_reject_bad_mass(self):
  with self.assertRaises(ValueError):f.parse_rns('1.0 5.0 11.1 346.5 2.2',1e15,.98)
 def test_parser_reject_missing_row(self):
  with self.assertRaises(ValueError):f.parse_rns('error in fluid',1e15,.98)
 def test_seven_models_not_original(self):
  self.assertTrue(all(x in f.EOS for x in ['APR4_EPP','ENG','WFF1']))
 def test_exact_spin_target(self):self.assertAlmostEqual(f.TARGET_HZ,346.536369)
 def test_numeric_2d_root_synthetic_mock(self):
  # Toy mapping only for mathematical root / failure propagation, not physics.
  def mock_eval(binary,table,ec,ratio):
   u=ec/1e15
   return {'mass_msun':2.073+1.7*(u-1.75)+.2*(ratio-.985),
    'spin_hz':346.536369+12000*(.985-ratio)+5*(u-1.75),
    'radius_eq_km':11.2+.2*(u-1.75),'central_energy_density_g_cm3':ec,
    'axis_ratio':ratio}
  with patch.object(f,'eval_rns',mock_eval):
   r=f.solve_one(Path('mock'),Path('mock'),1.75e15,seed_ratios=(.985,.980))
  self.assertEqual(r['status'],'DIRECT_RNS_MASS_SPIN_ROOT_PASS')
  self.assertLess(abs(r['root']['mass_spin_residual'][0]),f.M_TOL)
  self.assertLess(abs(r['root']['mass_spin_residual'][1]),f.HZ_TOL)
 def test_fail_closed_rns_failing(self):
  with patch.object(f,'eval_rns',side_effect=RuntimeError('synthetic failure')):
   r=f.solve_one(Path('mock'),Path('mock'),1.75e15,seed_ratios=(.985,))
  self.assertEqual(r['status'],'NOT_VALIDATED_RNS_ROOT')
if __name__=='__main__':unittest.main(verbosity=2)
