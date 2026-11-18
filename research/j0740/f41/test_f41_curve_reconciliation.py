import io, pathlib, sys, tempfile, unittest, zipfile, json
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import f41_curve_reconciliation as f

DIR=pathlib.Path(__file__).resolve().parent
P39=DIR/'J0740_F39_Causal_APR4_Integrated_Likelihood_20261118.zip'
P38=DIR/'J0740_F38_Source_Marginal_Likelihood_20261117.zip'
P165=DIR/'J0740_apr4_165_roots_20261118.zip'
GATE=DIR/'inputs/J0740_FULL_SOURCE_NATIVE_7EOS_GATE_20261116.json'

class TestF41(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.result=f.audit(P39,P38,P165,json.loads(GATE.read_text()))
 def test_archive_locks(self):
  self.assertEqual(f.sha256(P39),f.F39_HASH)
  self.assertEqual(f.sha256(P38),f.F38_HASH)
  self.assertEqual(f.sha256(P165),f.ROOT165_HASH)
 def test_true_source_table_hashes_differ(self):
  self.assertFalse(self.result['identical_table_sha256'])
  self.assertNotEqual(*self.result['source_EOS_table_sha256'].values())
 def test_25_point_cross_grid_comparison(self):
  x=self.result['geom_cross_check']
  self.assertEqual(x['count'],25)
  self.assertLess(x['max_abs_delta_m'],12)
  self.assertFalse(x['source_table_identity_inferred'])
 def test_six_surface_shared_window_likelihood(self):
  d=self.result['F38_six_grids_common_window_cross_check']
  self.assertEqual(len(d),6)
  self.assertLess(self.result['max_abs_F38_integral_percent_difference'],0.05)
 def test_six_integral_reproduces_original_f39(self):
  d=self.result['F38_six_grids_common_window_cross_check']
  self.assertAlmostEqual(d['posterior_prior_ratio_weighted_0.025_0.35.npz']['F39_25_direct'],0.7090184257438438,places=11)
 def test_source_gate_single_onstar_not_global(self):
  d=self.result['physical_source_7EOS_gate']
  self.assertEqual(d['onstar_sampled_screen_pass_count'],1)
  self.assertEqual(d['raw_whole_table_node_screen_pass_count'],0)
  self.assertTrue(d['per_eos']['APR4_EPP']['source_sampled_onstar_pass'])
  self.assertFalse(d['per_eos']['APR4_EPP']['source_whole_tabulation_node_causality_pass'])
 def test_source_gate_six_cannot_be_labelled_admissible(self):
  d=self.result['physical_source_7EOS_gate']['per_eos']
  self.assertTrue(all(not d[x]['source_sampled_onstar_pass'] for x in f.SOURCE_NAMES[1:]))
  self.assertTrue(all(d[x]['global_physical_model_acceptance']=='NOT_ESTABLISHED' for x in f.SOURCE_NAMES))
 def test_masses_unsorted_rejected(self):
  with zipfile.ZipFile(P165) as z: j=json.loads(z.read('J0740_APR4_FIXED_FREQUENCY_CURVE_F38_INTEGRAL.json'))
  roots=j['central_density_sweep'][:]
  roots[1],roots[3]=roots[3],roots[1]
  with self.assertRaises(ValueError): f.ascending_domain(roots)
 def test_empty_eos_family_rejected(self):
  with self.assertRaises(ValueError): f.physical_admissibility({})
 def test_outside_mass_support_rejected(self):
  with zipfile.ZipFile(P165) as z:j=json.loads(z.read('J0740_APR4_FIXED_FREQUENCY_CURVE_F38_INTEGRAL.json'))
  m,r,_=f.ascending_domain(j['central_density_sweep'])
  with self.assertRaises(ValueError): f.compare_at_same_masses([{'target_mass_msun':3.+i*.01,'radius_eq_km':11} for i in range(25)],m,r)
 def test_invalid_archive_fails_closed(self):
  with tempfile.TemporaryDirectory() as td:
   bad=pathlib.Path(td)/P165.name
   bad.write_bytes(b'invalid source')
   with self.assertRaises(ValueError):f.validate_source_files(P39,P38,bad)
 def test_never_final_bayes(self):
  self.assertEqual(self.result['final_seven_EOS_Bayes'],'NOT_RUN')
  self.assertIn('NOT_SEVEN_EOS_BAYES',self.result['status'])

if __name__=='__main__': unittest.main()
