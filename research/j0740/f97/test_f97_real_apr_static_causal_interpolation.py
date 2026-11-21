"""Source-native real CompOSE APR 328 nine-point static GR radial confirmation.
Independent physical acceptance: 7 PCHIP-causal vs 2 false-positive interpolation
modes. This test MUST NOT convert acausal positive omega2 to physical stability.
"""
from pathlib import Path
import unittest,json,hashlib,sys,math
import numpy as np
ROOT=Path(__file__).resolve().parent
REF=ROOT/'f95_reference' if (ROOT/'f95_reference/f95_static_radial_modes.py').is_file() else ROOT.parent/'f95'
sys.path.insert(0,str(REF))
import f95_static_radial_modes as physics
RESULT=ROOT/'F97_new_source_causal_9point_real_static_GR_eigenmodes_20261121.json'
DESIGN=ROOT/'F96_source_locked_real_dual_grid_preflight_20261121.json'
if not DESIGN.exists():DESIGN=ROOT.parent/'f96'/'F96_source_locked_real_dual_grid_preflight_20261121.json'
class SourceNativeTrueStaticCausalEvidence(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.d=json.loads(DESIGN.read_text())
  cls.r=json.loads(RESULT.read_text())
  cls.P,cls.E,eos,cls.nb,cls.cs=physics.prepare()
  cls.eos=staticmethod(eos)
 def test_original_genuine_publication_archive_sha(self):
  self.assertEqual(hashlib.sha256((REF/'source'/'F87_verified_publisher_original.zip').read_bytes()).hexdigest(),
   '8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12')
  self.assertEqual(self.r['original_source_publisher_SHA256'],self.d['original_328_APR_publisher_sha256'])
  self.assertEqual(len(self.P),1833)
 def test_source_native_first_acausal_vs_interpolation_crossing(self):
  self.assertEqual(int(np.sum(self.cs>1)),24)
  nativeP=float(self.P[np.flatnonzero(self.cs>1)[0]])
  interpolationP=self.r['F95_interpolation_first_causality_failure_pressure_MeVfm3']
  self.assertAlmostEqual(nativeP,448.88938082526886,places=5)
  self.assertAlmostEqual(interpolationP,437.59495115658586,places=4)
  self.assertGreater(nativeP-interpolationP,11.0)
  self.assertLess(nativeP-interpolationP,11.5)
 def test_native_source_last_good_secant_under_speed_light(self):
  self.assertEqual(self.r['native_first_acausal_source_secant_at_P_MeVfm3'],float(self.P[np.where(np.diff(self.P)/np.diff(self.E)>1)[0][0]]))
  self.assertAlmostEqual(self.r['previous_source_secant_cs2'],.995387797401608,places=7)
  self.assertLess(self.r['previous_source_secant_cs2'],1.)
 def test_nine_new_source_real_TOV_and_two_mesh_eigenmode_computations(self):
  self.assertEqual(self.r['source_static_stars'],9)
  self.assertEqual(self.r['radial_eigenmode_numerical_solves'],18)
  self.assertEqual(len(self.r['new_physical_real_source_static_stars']),9)
  for expected,src in zip(self.d['same_absolute_density_both_grids_g_cm3'],self.r['new_physical_real_source_static_stars']):
   self.assertEqual(src['source_input_rho_g_cm3'],expected)
   self.assertEqual([v['elements'] for v in src['static_radial_modes']],[240,440])
   self.assertTrue(all(v['omega2_kmminus2']>0 and v['mode_nodes'][0]==0 for v in src['static_radial_modes']))
   a,b=[v['fundamental_radial_Hz'] for v in src['static_radial_modes']]
   self.assertLess(abs(a-b)/b,.0004)
 def test_precisely_seven_physical_two_acausal_interpolation(self):
  self.assertEqual(self.r['F95_interpolated_physically_causal_static_star_count'],7)
  self.assertEqual(self.r['F95_interpolated_rejected_static_star_count'],2)
  self.assertEqual([v['F95_interpolated_static_model_causal'] for v in self.r['new_physical_real_source_static_stars']],[True]*7+[False]*2)
  self.assertFalse(self.r['new_physical_real_source_static_stars'][-1]['F95_interpolated_static_model_causal'])
  self.assertGreater(self.r['new_physical_real_source_static_stars'][-1]['central_logPchip_dp_de_c2'],1.0)
 def test_independent_real_TOV_recompute_one_extreme_physical_model(self):
  row=self.r['new_physical_real_source_static_stars'][6]
  star=physics.make_star(row['source_interpolated_pressure_MeVfm3'],self.eos,self.P)
  self.assertLess(abs(star['M']/physics.MKM-row['static_mass_Msun']),1e-6)
  self.assertLess(abs(star['R']-row['static_R_km']),.0003)
 def test_interpolated_crossing_reaches_actual_causal_rho_before_source(self):
  c=self.r['F95_interpolation_first_causality_failure_rho_g_cm3']
  n=self.d['first_source_acausal_limit_g_cm3']
  self.assertLess(c,n)
  self.assertLess(c,self.r['new_physical_real_source_static_stars'][7]['source_input_rho_g_cm3'])
 def test_do_not_confuse_gr_radial_static_with_rotating_eigenmode(self):
  self.assertEqual(self.r['rotating_star_dynamic_axisymmetric_stability'],'NOT_RUN')
  self.assertEqual(self.r['full_seven_EOS_native_photon_Bayes'],'NOT_RUN')
  self.assertEqual(self.r['native_C_RNS_evaluations_in_this_STATIC_run'],0)
  self.assertEqual(self.r['native_source_XPSI_photons_in_this_run'],0)
 def test_source_density_mass_monotonic_real_stars_not_global_theorem(self):
  a=self.r['new_physical_real_source_static_stars']
  self.assertTrue(all(a[i]['static_mass_Msun']<a[i+1]['static_mass_Msun'] for i in range(6)))
  self.assertTrue(all(a[i]['static_R_km']>a[i+1]['static_R_km'] for i in range(6)))
if __name__=='__main__':unittest.main()