import unittest
from pathlib import Path
from scipy.optimize import brentq
import sys
sys.path.insert(0,str(Path(__file__).parent))
import f48_wff1_nested_bracket_root as f

LOW={'central_energy_density_g_cm3':1.89e15,'axis_ratio':.98816,'mass_msun':2.01,'spin_hz':f.TARGET_FREQ}
UP={'central_energy_density_g_cm3':1.94e15,'axis_ratio':.98842,'mass_msun':2.025,'spin_hz':f.TARGET_FREQ}
class Tests(unittest.TestCase):
 def test_target_original_source_identifiers(self):
  self.assertEqual(f.MISSING_M,2.0175);self.assertEqual(len(f.F46_WFF1_SHA),64)
 def test_direct_nested_root_synthetic(self):
  # This is a mathematical instrument check, NOT new RNS physics.
  def toy(ec,ratio):
   u=(ec/1e15-1.89)/.05
   optimal=.98816+u*.00026
   return {'central_energy_density_g_cm3':ec,'axis_ratio':ratio,
    'mass_msun':2.01+.015*u+.01*(ratio-optimal),
    'spin_hz':f.TARGET_FREQ+5000*(ratio-optimal),'radius_eq_km':10.1-.2*u}
  trace=[];root=f.nested_direct_root(toy,LOW,UP,trace=trace)
  self.assertAlmostEqual(root['mass_msun'],f.MISSING_M,places=7)
  self.assertAlmostEqual(root['spin_hz'],f.TARGET_FREQ,places=6)
  self.assertGreater(len(trace),10)
 def test_bad_mass_bracket_rejected(self):
  with self.assertRaisesRegex(ValueError,'BRACKET_REQUIRED'):
   f.nested_direct_root(lambda ec,r:None,UP,LOW)
 def test_spin_bracket_missing_fail_closed(self):
  def bad(ec,r):return {'mass_msun':2.015,'spin_hz':f.TARGET_FREQ+50}
  with self.assertRaisesRegex(ValueError,'NO_REAL_FIXED_FREQUENCY_BRACKET'):
   f.nested_direct_root(bad,LOW,UP)
if __name__=='__main__':unittest.main(verbosity=2)
