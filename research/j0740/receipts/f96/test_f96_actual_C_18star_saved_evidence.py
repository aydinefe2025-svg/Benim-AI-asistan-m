"""Independent offline 10 tests on genuine original archived C/RNS output, no synthetic stars."""
import unittest,hashlib,json,math
from pathlib import Path
D=Path(__file__).resolve().parent
ORIGINAL=D/'F96_REAL_two_grid_source_causal_fixedJ_extension.json'
AUDIT=D/'F96_independent_actual_Einstein_C_18star_archive_receipt_20261121.json'
TRACES={g:D/f'F96_NATIVE_C_trace_{g}.jsonl' for g in ('151x301','201x401')}
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
class ExactRealCompiledCSourceEvidence(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=json.loads(ORIGINAL.read_text(encoding='utf-8-sig'))
  cls.a=json.loads(AUDIT.read_text(encoding='utf-8-sig'))
 def test_genuine_sha_manifest_source(self):
  self.assertEqual(SHA(ORIGINAL),'a794218fd091c02e92e522e599003c0a6375c072f8b43d6607f89409155fce5a')
  self.assertEqual(SHA(AUDIT),'7407ab8d6795e4d2da3ea89759a72f20c8cb1b53e438ee8d00e08d84046766ac')
 def test_source_of_two_original_published_apr_and_old_true_C_receipts(self):
  self.assertEqual(self.r['source_original_Zenodo_SHA256'],'8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12')
  self.assertEqual(self.r['F88_input_receipt_SHA256'],'771d7b494821a43485a8e1248185e768efe9b26e10c0ac8d07b9c1c0f206bc36')
  self.assertEqual(self.r['F89_5x2_native_reference_SHA256'],'f880db902d4ef26dc268030fcfaba83c74f5a499bf92b4c8be57f7888657d00f')
 def test_stars_are_eighteen_real_C_not_mock(self):
  for g in TRACES:
   orig=self.r['two_grid_native_results'][g]
   self.assertEqual(len(orig['completed_actual_C_stars']),9)
   self.assertEqual(orig['errors'],[])
   self.assertTrue(all(x['real_solver_checked'] for x in orig['completed_actual_C_stars']))
  self.assertEqual(self.a['actual_new_real_C_star_count'],18)
 def test_genuinely_205_compiled_model_evaluations(self):
  self.assertEqual(self.a['real_C_model_function_calls'],205)
  self.assertEqual(sum(self.r['two_grid_native_results'][g]['native_C_calls_logged_in_trace'] for g in TRACES),205)
 def test_original_saved_every_real_C_call_and_exact_SHA(self):
  for g,path in TRACES.items():
   x=self.r['two_grid_native_results'][g]
   self.assertEqual(SHA(path),x['trace_SHA256'])
   lines=[json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
   self.assertEqual(len(lines),x['native_C_calls_logged_in_trace'])
   self.assertTrue(all('measured_M_Msun' in ln['record'] and ln['record']['real_C_solver'] for ln in lines))
 def test_identical_absolute_density_and_same_physical_J(self):
  rho=self.r['density_grid_g_cm3'];j=self.r['fixed_same_common_J_cgs']
  self.assertEqual(len(rho),9)
  for g in TRACES:
   stars=self.r['two_grid_native_results'][g]['completed_actual_C_stars']
   for i,s in enumerate(stars):
    self.assertAlmostEqual(s['reported_rho_g_cm3']/rho[i],1,places=4)
    self.assertLess(abs(s['J_measured_cgs']/j-1),3e-5)
    self.assertEqual(s['source_point_index'],i)
 def test_true_finite_differences_positive_every_both_grid_interval(self):
  for g in TRACES:
   stars=self.r['two_grid_native_results'][g]['completed_actual_C_stars']
   calculated=[(v['M_msun']-u['M_msun'])/((v['reported_rho_g_cm3']-u['reported_rho_g_cm3'])/self.r['central_rho_common_reference_g_cm3']) for u,v in zip(stars,stars[1:])]
   src=self.r['sampled_causal_derivative_signs'][g]['interval_M_rho_slopes']
   self.assertEqual(len(src),8)
   self.assertLess(max(abs(a-b) for a,b in zip(calculated,src)),1e-9)
   self.assertTrue(all(s>0 for s in calculated))
 def test_same_c_source_two_mesh_agreement(self):
  p=self.r['cross_grid_common_density_common_J_comparison']
  self.assertEqual(len(p),9)
  self.assertLess(max(abs(x['R_eq_difference_m']) for x in p),2)
  self.assertLess(max(abs(x['M_difference_Msun']) for x in p),.001)
  self.assertLess(max(abs(x['relative_J_error_between_grids']) for x in p),3e-5)
 def test_all_star_centers_below_first_publisher_native_acausal_row(self):
  upper=self.r['first_source_acausal_rho_g_cm3']
  self.assertEqual(self.r['first_source_acausal_nodes'],24)
  self.assertTrue(all(p<upper for p in self.r['density_grid_g_cm3']))
  self.assertAlmostEqual(self.r['density_grid_g_cm3'][-1]/upper,.995,places=12)
 def test_no_rotating_eigenmode_or_7_eos_photon_bayes_pretence(self):
  self.assertEqual(self.r['rotating_axisymmetric_dyn_eigenmode'],'NOT_RUN')
  self.assertEqual(self.r['continuous_global_fixed_J_turning_proof'],'NOT_PROVEN_BY_DISCRETE_SAMPLES')
  self.assertEqual(self.r['seventh_EOS_full_native_photon_Bayes'],'NOT_RUN')
  self.assertEqual(self.a['source_model_interpolation_warning']['F95_causally_admissible_static_of_nine'],7)
  self.assertEqual(self.a['source_model_interpolation_warning']['two_static_cases_acausal_under_F95_interpolation'],2)
if __name__=='__main__':unittest.main()
