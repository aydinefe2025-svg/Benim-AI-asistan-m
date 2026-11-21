"""F96 source-pinned math/guard tests; real C results only counted by workflow's native runner."""
import io,zipfile,json,hashlib,math,unittest,os
from pathlib import Path
from f96_source_causal_fixedJ_global_extension import (
 choose_grid,verify_input,audit_result,LOW_FRACTIONS,PUBLISHER_SHA,CAUSAL_MARGIN)
F88=Path(os.environ.get('F96_SOURCE_F88_ZIP','/mnt/data/J0740_F88_original_C_RNS_archive.zip'))
F89=Path(os.environ.get('F96_SOURCE_F89_ZIP','/mnt/data/F89_native_existing_20261120.zip'))

class ActualNativeSourceEvidence(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  # Source package is real F88/F89 GitHub C workflow artifacts downloaded in this turn.
  if not(F88.exists() and F89.exists()):
   raise RuntimeError('MISSING_GENUINE_F88_F89_SOURCE_ARTIFACT_NO_TEST_SKIP_ACCEPTED')
  with zipfile.ZipFile(F88) as z:
   cls.f88=json.loads(z.read('F88_REAL_two_grid_C_RNS.json'))
   cls.f88_sha=hashlib.sha256(z.read('F88_REAL_two_grid_C_RNS.json')).hexdigest()
   cls.mr_sha=hashlib.sha256(z.read('m.rns')).hexdigest()
  with zipfile.ZipFile(F89) as z:
   cls.f89=json.loads(z.read('F89_ACTUAL_two_grid_fixed_J_local_screen.json'))
   cls.f89_sha=hashlib.sha256(z.read('F89_ACTUAL_two_grid_fixed_J_local_screen.json')).hexdigest()
 def test_pinned_original_compose_publisher_zip(self):
  self.assertEqual(self.f88['audit']['original_COMPOSE_APR_sha256'],PUBLISHER_SHA)
  self.assertEqual(self.f88_sha,'771d7b494821a43485a8e1248185e768efe9b26e10c0ac8d07b9c1c0f206bc36')
 def test_genuine_F88_C_source_and_distinct_grids(self):
  self.assertEqual(self.mr_sha,'7643d0e4361adee77cc79d1b69eb445db70a52443b833c4dddafa973193fb580')
  self.assertEqual(set(self.f88['binary_sha256']),{'151x301','201x401'})
  self.assertEqual(len(set(self.f88['binary_sha256'].values())),2)
  self.assertTrue(all(x['real_C_solver'] for x in self.f88['actual_C_stars'].values()))
 def test_reuse_previous_real_F89_five_stars(self):
  self.assertEqual(self.f89_sha,'f880db902d4ef26dc268030fcfaba83c74f5a499bf92b4c8be57f7888657d00f')
  self.assertEqual(self.f89['publisher_original_SHA256'],PUBLISHER_SHA)
  self.assertTrue(all(len(x['points'])==5 and x['mass_strict_increasing'] for x in self.f89['grid_results'].values()))
  self.assertTrue(all(x['real_solver_checked'] for d in self.f89['grid_results'].values() for x in d['points']))
 def test_f96_two_grid_shared_physical_J(self):
  limit=self.f88['audit']['grids']['201x401']['causal_e_c_upper_g_cm3']
  rho,J,factors,densities=choose_grid(self.f88['actual_C_stars'],limit)
  self.assertEqual(len(densities),9)
  self.assertAlmostEqual(J,4.8245626795750385e48,delta=5e38)
  self.assertAlmostEqual(rho,1.7424097239425e15,delta=2)
  self.assertEqual(tuple(factors[:len(LOW_FRACTIONS)]),LOW_FRACTIONS)
  self.assertTrue(all(x<limit for x in densities))
 def test_stop_at_original_source_first_superluminal_barrier(self):
  limit=self.f88['audit']['grids']['151x301']['causal_e_c_upper_g_cm3']
  rho,J,factors,densities=choose_grid(self.f88['actual_C_stars'],limit)
  self.assertAlmostEqual(densities[-1],limit*(1-CAUSAL_MARGIN),delta=2)
  self.assertEqual(self.f88['audit']['source_referenced_high_density_superluminal_nodes'],24)
 def test_reject_missing_two_grid_physics(self):
  limit=self.f88['audit']['grids']['151x301']['causal_e_c_upper_g_cm3']
  with self.assertRaisesRegex(ValueError,'BASELINES'):
   choose_grid({'151x301':self.f88['actual_C_stars']['151x301']},limit)
 def test_reject_invalid_causal_domain(self):
  limit=self.f88['audit']['grids']['151x301']['causal_e_c_upper_g_cm3']
  with self.assertRaisesRegex(ValueError,'NO_CAUSAL_REGION'):
   choose_grid(self.f88['actual_C_stars'],limit*.8)
 def test_guard_non_native_star_before_dynamic_claim(self):
  limit=self.f88['audit']['grids']['151x301']['causal_e_c_upper_g_cm3']
  rho,J,factors,densities=choose_grid(self.f88['actual_C_stars'],limit)
  d={'fractional_central_rho_grid':factors,'density_grid_g_cm3':densities,
     'first_source_acausal_rho_g_cm3':limit,'first_source_acausal_nodes':24,
     'central_rho_common_reference_g_cm3':rho,
     'two_grid_native_results':{g:{'completed_actual_C_stars':[{'real_solver_checked':False,'source_point_index':0,'J_relative_error':0.0}], 'errors':[{'point_index':i} for i in range(1,9)]} for g in ('151x301','201x401')}}
  with self.assertRaisesRegex(ValueError,'SYNTHETIC_C_SOURCE_REJECTED'):
   audit_result(None,d)
 def test_real_C_must_have_two_independent_grids(self):
  self.assertEqual(self.f89['F88_source_C_binary_sha256'],self.f88['binary_sha256'])
  self.assertEqual(self.f89['is_full_global_stability'],'NO')
  self.assertEqual(self.f89['mode_eigenfrequency_calculation'],'NOT_RUN')
if __name__=='__main__':unittest.main()