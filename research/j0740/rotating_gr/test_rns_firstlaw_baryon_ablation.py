import unittest
from rns_firstlaw_baryon_ablation import strict_replace,parse_c_run,patch_isolated_rns

class TestAblationGuards(unittest.TestCase):
 def test_fail_if_pinned_C_anchor_missing(self):
  with self.assertRaises(ValueError):strict_replace('nothing','expected','replacement')
 def test_fail_if_anchor_duplicated(self):
  with self.assertRaises(ValueError):strict_replace('xx xx','xx','a')
 def test_accept_unique_C_anchor(self):
  self.assertEqual(strict_replace('one xx two','xx','y'),'one y two')
 def test_strict_stderr_baryon_print(self):
  v=parse_c_run('1.749 2.073 10.76 346.5\n','J0740_MASS0_MSUN 2.437298765\n')
  self.assertEqual(v['baryonic_mass_msun'],2.437298765)
 def test_reject_missing_M0(self):
  with self.assertRaises(RuntimeError):parse_c_run('1.749 2.073 10.76 346.5\n','')
 def test_reject_duplicate_M0(self):
  with self.assertRaises(RuntimeError):parse_c_run('1.749 2.073 10.76 346.5\n','J0740_MASS0_MSUN 2.1\nJ0740_MASS0_MSUN 2.2\n')
 def test_reject_nonphysical_numeric(self):
  with self.assertRaises(RuntimeError):parse_c_run('nan 0 0 0\n','J0740_MASS0_MSUN 2.1\n')

if __name__=='__main__':unittest.main()
