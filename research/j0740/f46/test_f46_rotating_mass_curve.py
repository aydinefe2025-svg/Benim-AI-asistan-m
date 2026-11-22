"""F46 synthetic tests only: real C GR solver runs in pinned GitHub Actions."""
import unittest, tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
import f46_rotating_mass_curve as f

BASE={'central_energy_density_g_cm3':1.7e15,'axis_ratio':.98,'mass_msun':2.073,
 'spin_hz':f.OBSERVED_FREQ,'radius_eq_km':11.7}

class Tests(unittest.TestCase):
 def test_pinned_mass_grid(self):
  self.assertAlmostEqual(min(f.MASS_GRID),1.95);self.assertAlmostEqual(max(f.MASS_GRID),2.10)
  self.assertEqual(len(f.MASS_GRID),22);self.assertIn(2.073,f.MASS_GRID)
 def test_source_anchors_are_pinned(self):
  self.assertEqual(len(f.prev.EOS),7);self.assertEqual(len(f.F42_SHA),64)
 def test_valid_root(self):self.assertTrue(f.validate_root(BASE,2.073))
 def test_bad_mass_rejected(self):
  bad=dict(BASE,mass_msun=2.5);self.assertFalse(f.validate_root(bad,2.073))
 def test_bad_frequency_rejected(self):
  bad=dict(BASE,spin_hz=400);self.assertFalse(f.validate_root(bad,2.073))
 def test_bad_axis_ratio_rejected(self):
  bad=dict(BASE,axis_ratio=.6);self.assertFalse(f.validate_root(bad,2.073))
 def test_full_grid_toy(self):
  def fake(binary,table,target,seed):
   v=dict(BASE,mass_msun=target,central_energy_density_g_cm3=(1.7+(target-2.073)*.4)*1e15)
   v['target_mass_msun']=target
   return {'status':'MATCHED_DIRECT_C_GR_ROOT','root':v}
  result=f.solve_curve('MPA1',Path('mock'),BASE,Path('mock'),solve=fake,exploratory=False)
  self.assertTrue(result['common_window_all_roots_present'])
  self.assertEqual(result['successful_common_targets'],22)
  self.assertTrue(result['rising_density_order_pass'])
 def test_fail_closed_if_mass_missing(self):
  def fake(binary,table,target,seed):
   if target>2.09:return {'status':'NUMERICAL_ROOT_FAILED'}
   v=dict(BASE,mass_msun=target,central_energy_density_g_cm3=(1.7+(target-2.073)*.4)*1e15);v['target_mass_msun']=target
   return {'status':'MATCHED_DIRECT_C_GR_ROOT','root':v}
  result=f.solve_curve('MPA1',Path('mock'),BASE,Path('mock'),solve=fake,exploratory=False)
  self.assertFalse(result['common_window_all_roots_present'])
 def test_guard_wrong_eos(self):
  with self.assertRaises(ValueError):f.solve_curve('NOT_AN_EOS',Path('x'),BASE,Path('x'))
 def test_real_2d_mock_solver(self):
  def mk(bin,table,ec,rat):
   x=ec/1e15
   return {'central_energy_density_g_cm3':ec,'axis_ratio':rat,
      'mass_msun':2.073+(x-1.7)*1.5+(rat-.98)*.2,
      'spin_hz':f.OBSERVED_FREQ+(rat-.98)*5000+(x-1.7)*2,
      'radius_eq_km':11.7+(x-1.7)*.25}
  result=f.direct_fixed_mf(Path('mock'),Path('mock'),2.085,BASE,eval_model=mk)
  self.assertEqual(result['status'],'MATCHED_DIRECT_C_GR_ROOT')
 def test_one_corrupt_archived_source(self):
  with tempfile.TemporaryDirectory() as d:
   a=Path(d)/'a.zip';a.write_bytes(b'bad')
   with self.assertRaisesRegex(ValueError,'PINNED_INPUT_ARCHIVE_SHA_MISMATCH'):f.check_archives(a,a)
if __name__=='__main__':unittest.main(verbosity=2)
