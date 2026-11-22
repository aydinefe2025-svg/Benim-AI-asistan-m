"""F98 regression over real 1933 source nodes and 18 previously computed native C stars."""
import hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R))
import f98_rns_source_interpolation_repair as src

class RealAPRSourceCubicCausality(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.real=src.load_rns(R/'F88_m_original.rns')
  cls.old=src.load_previous_f96(R/'F96_real_18_source_C_models.json')
  cls.repaired=src.add_exact_original_knot_intermediates(cls.real)
  cls.report=json.loads((R/'F98_true_C_RNS_fourpoint_EOS_causality_20261122.json').read_text())
 def test_source_sha_original_true_f88_and_f96_18_real_C(self):
  self.assertEqual(src.digest((R/'F88_m_original.rns').read_bytes()),src.ORIGINAL_RNS_SHA)
  self.assertEqual(src.digest((R/'F96_real_18_source_C_models.json').read_bytes()),src.F96_SOURCE_RESULT_SHA)
  self.assertEqual(sum(len(v['completed_actual_C_stars']) for v in self.old['two_grid_native_results'].values()),18)
 def test_1933_source_nodes_and_all_four_original_physical_columns_unchanged(self):
  self.assertEqual(self.real.shape,(1933,4));self.assertEqual(self.repaired.shape,(1943,4))
  for j in range(len(self.real)):
   shift=sum(n for i,n in src.INSERTS.items() if i<j)
   self.assertTrue(np.array_equal(self.repaired[j+shift],self.real[j]),(j,shift))
 def test_candidate_bytes_are_frozen_sha(self):
  self.assertEqual(src.digest((R/'m_rns_1943_candidate.rns').read_bytes()),'d62d490dd106f7995cb96563bcb438de8c934375cca4fb04d9010b6300a8cff9')
 def test_original_18_have_mechanically_negative_sound_speed_sq_somewhere(self):
  a=self.report['original_numerical_EOS']
  self.assertEqual(a['negative_sound_speed_squares_in_all_stars'],18)
  self.assertEqual(a['stars_thermodynamically_causal_all_interior'],0)
  self.assertEqual({tuple(x['negative_intervals']) for x in a['nine_original_cubic_core_audits']},{(1830,)})
  lo=src.extrema_segment(self.real,1830)
  self.assertAlmostEqual(lo['min_cs2'],-.0004400867659354485,places=9)
 def test_original_final_two_have_early_superluminal_sound_speed_sq(self):
  a=self.report['original_numerical_EOS']
  self.assertEqual(a['superluminal_central_or_interior_stars'],4)
  self.assertEqual([bool(x['superluminal_intervals']) for x in a['nine_original_cubic_core_audits']],[False]*7+[True]*2)
  self.assertAlmostEqual(src.extrema_segment(self.real,1908)['max_cs2'],1.0100666093221538,places=7)
 def test_10_added_rows_alone_repair_exact_source_C_4pt_pressures_at_all_9_centers(self):
  b=self.report['derived_new_distinct_interpolation_candidate']
  self.assertEqual(b['new_intermediate_rows'],10)
  self.assertEqual(b['nodes'],1943)
  self.assertTrue(all(x['passes_local_positive_causal_interpolated_P_e'] for x in b['nine_candidate_cubic_core_audits']))
  self.assertGreater(min(x['min_cs2'] for x in b['nine_candidate_cubic_core_audits']),0)
  self.assertLess(max(x['max_cs2'] for x in b['nine_candidate_cubic_core_audits']),1)
 def test_four_node_cubic_exact_source_log_interpolation_at_native_knots(self):
  for grid in (self.real,self.repaired):
   for i in [1800,1829,1830,1831,1907,1908]:
    if i+3>=len(grid):continue
    x0,y0,dx,poly=src.log_lagrange_four_coeffs(grid,i)
    self.assertAlmostEqual(y0+poly(0),np.log10(grid[i,1]/src.C**2),places=9)
    self.assertAlmostEqual(y0+poly(1),np.log10(grid[i+1,1]/src.C**2),places=9)
 def test_exact_polynomial_extrema_capture_internal_derivative_signs(self):
  for a in (self.real,self.repaired):
   for i in (1830,1908):
    val=src.extrema_segment(a,i)
    coef=src.log_lagrange_four_coeffs(a,i)
    fn=src.cs2_function_from_coeffs(coef)
    q=np.linspace(0,1,101);f=np.asarray([fn(t) for t in q]);tol=1e-9
    self.assertGreaterEqual(float(np.min(f))+tol,val['min_cs2'])
    self.assertLessEqual(float(np.max(f))-tol,val['max_cs2'])
 def test_source_firstlaw_and_rotating_modes_not_falsely_certified(self):
  c=self.report['physics_implications']
  self.assertIn('NOT_PROVEN',c['candidate_continuous_first_law_and_chemical_potential'])
  self.assertEqual(c['candidate_true_native_Einstein_rotating_C_stars'],'NOT_RUN_UNTIL_GITHUB_CI')
  self.assertEqual(c['axisymmetric_rotating_dynamic_modes'],'NOT_RUN')
  self.assertEqual(c['seven_EOS_full_source_native_photon_Bayes'],'NOT_RUN')
 def test_fail_closed_if_wrong_old_source(self):
  from tempfile import TemporaryDirectory
  with TemporaryDirectory() as d:
   p=Path(d)/'wrong.rns';p.write_bytes((R/'F88_m_original.rns').read_bytes()+b'X')
   with self.assertRaisesRegex(ValueError,'SHA'):src.load_rns(p)

if __name__=='__main__':unittest.main()
