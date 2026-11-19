"""Fail-closed regression checks for actual original 7-source C RNS mass sweeps."""
import pathlib,unittest,sys,tempfile
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import native_original_seven_spin_sweep as m

class OriginalSevenSweepTests(unittest.TestCase):
 def test_exact_original_label_set(self):
  self.assertEqual(set(m.SEVEN),{'APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2'})
  self.assertEqual(set(m.SEVEN),set(m.PREVIOUS_DIRECT_C_M2073))
 def test_original_source_hashes_seven_independent(self):
  self.assertEqual(len(set(m.SEVEN.values())),7)
  self.assertTrue(all(len(s)==64 for s in m.SEVEN.values()))
 def test_mass_prior_continuation_spans_measured_mass(self):
  self.assertLess(m.LOW_FACTOR,1)
  self.assertGreater(m.HIGH_FACTOR,1)
  self.assertGreaterEqual(m.NUM_MODELS,30)
 def test_target_source_reference_not_synthetic(self):
  self.assertAlmostEqual(m.PREVIOUS_DIRECT_C_M2073['MPA1'],12.533295930)
  self.assertAlmostEqual(m.PREVIOUS_DIRECT_C_M2073['WFF2'],10.623929893)
 def test_branch_rejects_insufficient_actual_RNS_C_models(self):
  with self.assertRaisesRegex(ValueError,'too few'):
   m.choose_first_mass_increasing_branch([{'mass_msun':1.8,'central_energy_density_g_cm3':5e14}])
 def test_branch_rejects_no_target_mass_crossing(self):
  a=[{'mass_msun':1.30+i*.025,'central_energy_density_g_cm3':5e14+i*1e13} for i in range(15)]
  with self.assertRaisesRegex(ValueError,'does not bracket'):
   m.choose_first_mass_increasing_branch(a)
 def test_branch_identifies_first_mass_maximum(self):
  a=[{'mass_msun':1.6+i*.05,'central_energy_density_g_cm3':5e14+i*1e13} for i in range(15)]
  a.extend([{'mass_msun':2.29-i*.05,'central_energy_density_g_cm3':7e14+i*1e13} for i in range(3)])
  good,peak,rejected=m.choose_first_mass_increasing_branch(a)
  self.assertLess(peak,17)
  self.assertGreater(len(good),10)
  self.assertGreater(good[-1]['mass_msun'],m.MASS)
 def test_exact_spin_stated_not_be_relabelled(self):
  self.assertAlmostEqual(m.OBSERVED_SPIN_HZ,346.536369,places=6)
  self.assertLessEqual(m.CURVE_MASS_VALIDATION_TOL_KM,.05)
 def test_unverified_original_source_fails_early(self):
  with self.assertRaises(ValueError):
   m.seed_source(pathlib.Path('/doesnotexist'),pathlib.Path('/doesnotexist'),'UNKNOWN')


 def test_late_timeout_accepted_only_after_real_sampled_mass_turnover(self):
  def models(ms):
   return [{'mass_msun':float(v),'central_energy_density_g_cm3':5e14+i*1e13} for i,v in enumerate(ms)]
  source=[.95+i*.033 for i in range(37)]+[2.14,2.135,2.13]
  self.assertTrue(m.original_late_timeout_after_witnessed_mass_peak(models(source)))
  self.assertFalse(m.original_late_timeout_after_witnessed_mass_peak(models(source[:-2])))
  self.assertFalse(m.original_late_timeout_after_witnessed_mass_peak(models([.95+i*.025 for i in range(40)])))
 def test_early_rns_timeout_still_fails_closed(self):
  a=[{'mass_msun':1.7+i*.01,'central_energy_density_g_cm3':5e14+i*1e13} for i in range(30)]
  self.assertFalse(m.original_late_timeout_after_witnessed_mass_peak(a))

if __name__=='__main__':unittest.main()
