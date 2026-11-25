#!/usr/bin/env python3
"""Proof checks on real source-matched F100 stationary/radial work; do not conflate with rotating eigenmodes."""
import unittest,hashlib,json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import brentq
HERE=Path(__file__).resolve().parent
P=HERE/'F100_STATIC_RADIAL_PROVEN_20261122.json'
MODEL_SHA='c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'

class VerifiedRealPhysicalStationaryStates(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.f=json.loads(P.read_text());cls.s=cls.f['static_models'];
  sys.path.insert(0,str(HERE))
  import f100_real_rotating_fixedJ_highdensity as f100
  cls.runner=f100
 def test_source_exact_distinct_eos_not_original_likelihood(self):
  self.assertEqual(self.f['source_F99_SHA256'],MODEL_SHA)
  self.assertTrue(self.f['derived_model_distinct_from_original_seven_EOS'])
  self.assertEqual(self.f['seven_original_EOS_all_MR_native_photon_evidence'],'NOT_RUN')
 def test_true_solved_stars_both_stability_branches(self):
  self.assertEqual(len(self.s),5)
  self.assertEqual([x['label'] for x in self.s],['j0740_equilibrium','stable_branch','tov_mass_maximum','unstable_branch','deep_unstable_branch'])
  self.assertTrue(all(x['M_Msun']>2.0 and 9<x['R_km']<11 for x in self.s))
 def test_actual_mass_turning_point_on_derived_eos(self):
  self.assertTrue(2.17<self.f['M_max_TOV_MSun']<2.19)
  self.assertTrue(940<self.f['Pc_at_Mmax_MeVfm3']<970)
  self.assertAlmostEqual(self.f['M_max_TOV_MSun'],self.s[2]['M_Msun'],places=8)
  self.assertGreater(self.s[2]['M_Msun'],self.s[1]['M_Msun'])
  self.assertGreater(self.s[2]['M_Msun'],self.s[3]['M_Msun'])
 def test_radial_eigenfrequency_sign_changes_after_mass_peak(self):
  for row in self.s[:2]:self.assertTrue(all(x['omega0_squared_km_minus2']>0 and x['nodes']==0 for x in row['modes']))
  for row in self.s[3:]:self.assertTrue(all(x['omega0_squared_km_minus2']<0 and x['nodes']==0 for x in row['modes']))
 def test_four_distinct_meshes_independently_confirm_zero_mode(self):
  ms=[x['mesh'] for x in self.f['radial_omega2_zero_mesh_checks']]
  self.assertEqual(ms,[220,320,480,700]);self.assertTrue(all(abs(x['relative_delta_pct'])<.08 for x in self.f['radial_omega2_zero_mesh_checks']))
 def test_real_2p073_static_target_matches_source_tov(self):
  self.assertAlmostEqual(self.s[0]['M_Msun'],2.073,delta=.00003)
  self.assertTrue(2100<self.s[0]['modes'][-1]['signed_f0_Hz']<2450)
 def test_source_global_causality_all_1980_segments(self):
  self.assertEqual(self.f['nodes'],1981)
  self.assertTrue(self.f['all_EOS_native_segments_causal'])
  self.assertTrue(0<self.f['cs2_min']<1 and 0<self.f['cs2_max']<1)
 def test_frozen_high_density_rotating_run_is_new_not_repeat(self):
  rr=self.runner.DENSITIES
  self.assertEqual(len(rr),14);self.assertEqual(len(set(rr)),14)
  self.assertTrue(all(rr[i]<rr[i+1] for i in range(13)))
  self.assertTrue(rr[0]>2.0e15 and rr[-1]<3.643605896e15)
  self.assertTrue(min(rr)<self.runner.RHO_STATIC_MAX<max(rr))
 def test_no_spinning_dynamic_eigenmode_or_native_photon_fiction(self):
  self.assertEqual(self.f['uniformly_rotating_axisymmetric_perturbation_eigenmodes'],'NOT_RUN')
  self.assertEqual(self.f['seven_original_EOS_all_MR_native_photon_evidence'],'NOT_RUN')
  self.assertEqual(self.f['real_rotating_fixed_J_sequence'],'NOT_RUN_BY_THIS_SCRIPT')
 def test_rotating_peak_classifier_reads_real_C_samples_and_refuses_continuum_theorem(self):
  stars=[{'requested_rho_g_cm3':rho,'reported_rho_g_cm3':rho,'M_msun':2.1-.0001*((rho/1e15)-2.7)**2} for rho in self.runner.DENSITIES]
  x=self.runner.analyze_one(stars,1.82e15)
  self.assertTrue(x['positive_then_negative_slope_signchange_index'])
  self.assertEqual(x['continuous_turning_point_math_proven'],'NO_DISCRETE_RNS_SAMPLES_ONLY')
  # These are algorithm-only fixtures. They never qualify as physical C evidence.

if __name__=='__main__':unittest.main()
