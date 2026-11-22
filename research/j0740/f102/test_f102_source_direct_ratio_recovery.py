#!/usr/bin/env python3
"""Only source real original receipt and physical math checks; no synthetic stars."""
import os,sys,unittest,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import f102_direct_axis_ratio_recovery as f
ROOT=Path(__file__).resolve().parent
F100=Path(os.environ.get('F102_F100_ZIP','/mnt/data/J0740_F100_REAL_C_24_28_original_partial_20261122.zip'))
F101=Path(os.environ.get('F102_F101_ZIP','/mnt/data/J0740_F101_1_of_4_root_recovery_source_logs.zip'))

class F102RealOriginalNativeSources(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original,cls.recovered=f.read_data(F100,F101)
 def test_original_F100_cannot_change(self):
  self.assertEqual(f.sha(F100.read_bytes()),f.F100_ZIP)
 def test_original_F101_cannot_change(self):
  self.assertEqual(f.sha(F101.read_bytes()),f.F101_ZIP)
 def test_original_24_true_C_stars_remain(self):
  self.assertEqual(self.original['native_real_C_stars'],24)
  self.assertEqual(sum(len(v['actual_C_stars']) for v in self.original['two_grid_results'].values()),24)
  self.assertEqual(self.original['new_native_C_calls'],399)
 def test_f101_one_true_C_star_kept_not_rerun(self):
  self.assertEqual(self.recovered['source_point_index'],6)
  self.assertEqual(self.recovered['recovered_original_C'],'F101_double_SetSpin_9_true_original_C_calls_source_trace_locked')
  self.assertLess(self.recovered['J_relative_error'],1e-8)
 def test_remaining_three_exact_original_indexes(self):
  self.assertEqual(f.STILL_MISSING,{'151x301':(12,),'201x401':(11,12)})
  self.assertEqual([e['source_point_index'] for e in self.original['two_grid_results']['201x401']['real_C_errors']],[6,11,12])
 def test_distinct_fixed_J_and_native_star_density(self):
  self.assertTrue(math.isclose(self.original['target_same_J_cgs'],f.TARGET_J,rel_tol=1e-14))
  self.assertEqual(len(self.original['predeclared_central_densities_g_cm3']),14)
 def test_real_ratio_branch_is_not_Ridder_float_patch(self):
  s=Path(f.__file__).read_text()
  self.assertIn("'-r',f'{ratio:.12f}'",s)
  self.assertIn("from f81_exact_mass_spin import parse_rns",s)
  self.assertNotIn("return {'real_solver_checked':True,'M_msun':2",s)
 def test_j_acceptance_never_loosened(self):
  self.assertEqual(f.J_REL_TOL,3e-5)
  self.assertTrue(all(0.70<x<1 for x in f.RATIOS))
  self.assertEqual(tuple(sorted(f.RATIOS,reverse=True)),f.RATIOS)
 def test_no_dyn_modes_and_no_fake_source_EOS(self):
  s=Path(f.__file__).read_text()
  self.assertIn("'rotating_dynamical_eigenfrequencies':'NOT_RUN'",s)
  self.assertIn("'seven_original_EOS_full_native_XPSI_photon_Bayes':'NOT_RUN'",s)

if __name__=='__main__':unittest.main()
