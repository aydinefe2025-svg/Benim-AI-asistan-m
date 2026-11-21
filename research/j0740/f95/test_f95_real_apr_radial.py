"""F95 real publisher static APR(APR) radial pulsations — numerical verification, not rotating stability."""
import hashlib,json,math,unittest
from pathlib import Path
import numpy as np
from f95_static_radial_modes import A,MKM,prepare,make_star,radial
R=Path(__file__).resolve().parent
DATA=R/'F95_real_APR_static_radial_eigenmodes_20261121.json'

class RealPublisherModes(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.o=json.loads(DATA.read_text())
  cls.P,cls.E,eos,cls.nb,cls.cs=prepare()
  cls.eos=staticmethod(eos)
 def test_genuine_source_archive_not_fixture(self):
  p=R/'source'/'F87_verified_publisher_original.zip'
  self.assertEqual(p.stat().st_size,250015)
  self.assertEqual(hashlib.md5(p.read_bytes()).hexdigest(),'ccc2fbef2b0f51df389ff8f7d9b00608')
  self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),self.o['source_original_sha256'])
  self.assertEqual(len(self.P),1833)
 def test_existing_native_source_acausality_not_hidden(self):
  self.assertEqual((self.cs>1).sum(),24)
  self.assertAlmostEqual(self.o['source_first_superluminal_P_MeVfm3'],448.88938082526886,places=4)
  self.assertGreater(self.o['source_first_superluminal_P_MeVfm3'],self.o['static_target_pc_MeVfm3'])
 def test_real_static_2073_root(self):
  x=make_star(self.o['static_target_pc_MeVfm3'],self.eos,self.P,rtol=5e-10,max_step=.025)
  self.assertAlmostEqual(x['M']/MKM,2.073,places=7)
  self.assertLess(abs(x['R']-self.o['static_target_R_km']),.001)
  self.assertLess(abs(x['R']-10.722),.01)
 def test_physical_segment_pchip_causality(self):
  pc=self.o['static_target_pc_MeVfm3']
  ps=np.geomspace(self.P[0],pc,3200)
  cs=np.array([self.eos(p*A)[1] for p in ps])
  g=np.array([self.eos(p*A)[2] for p in ps])
  self.assertTrue(np.all(np.isfinite(cs)) and np.all(cs>0) and np.all(cs<1))
  self.assertTrue(np.all(np.isfinite(g)) and np.all(g>0))
  self.assertLess(abs(np.max(cs)-self.o['physical_central_PCHIP_cs2_max']),.002)
 def test_all_four_radial_nodes_and_positive_fundamental(self):
  x=self.o['eigenmodes_meshes']
  self.assertEqual([g['N'] for g in x],[320,640,960])
  for grid in x:
   self.assertEqual(grid['node_counts'],[0,1,2,3])
   self.assertTrue(all(y>0 for y in grid['eigen_omega2_kmminus2']))
   self.assertTrue(all(grid['eigen_omega2_kmminus2'][i]<grid['eigen_omega2_kmminus2'][i+1] for i in range(3)))
  self.assertTrue(self.o['fundamental_radial_omega_squared_positive'])
  self.assertGreater(self.o['first_mode_omega2_kmminus2'],0.0023)
 def test_mesh_and_background_tov_convergence(self):
  a=self.o
  self.assertLess(a['f0_mesh320_960_rel_difference'],.0005)
  self.assertLess(abs(a['fine_TOV_R_diff_m']),.5)
  self.assertLess(abs(a['fine_TOV_M_diff_Msun']),1e-6)
  self.assertLess(abs(a['fine_TOV_frequency_diff_Hz_at_mesh640']),1.)
 def test_independently_recompute_eigenmode_with_new_solver_settings(self):
  x=make_star(self.o['static_target_pc_MeVfm3'],self.eos,self.P,rtol=2e-10,max_step=.019)
  z=radial(x,self.eos,self.P,N=440)
  self.assertEqual(z['node_counts'][0],0)
  self.assertGreater(z['eigen_omega2_kmminus2'][0],0)
  self.assertLess(abs(z['signed_frequency_hz'][0]-self.o['fundamental_radial_f_Hz']),2.)
 def test_source_acausal_turning_is_only_numerical(self):
  a=self.o
  maxpc=a['acausal_branch_max_mass_numeric_only']['pc_MeVfm3']
  mode0=a['acausal_branch_radial_zero_mode_crosscheck_NUMERICAL_ONLY']['650']['pc_zero_radial_MeVfm3']
  self.assertLess(abs(maxpc-mode0),.5)
  self.assertGreater(maxpc,a['source_first_superluminal_P_MeVfm3'])
  self.assertIn('NOT a physically valid EOS',a['important_no_go'])
 def test_no_rotating_or_photon_eos_conclusion(self):
  a=self.o
  self.assertEqual(a['angular_momentum_J'],'0_STATIC_ONLY')
  self.assertEqual(a['spinning_star_axisymmetric_dynamic_stability'],'NOT_PROVEN')
  self.assertEqual(a['full_photon_EOS_Bayes'],'NOT_RUN')
  self.assertEqual(a['photon_likelihood_new_calls'],0)
  self.assertTrue(a['previous_EOS_323_C_RNS_not_repeated'])

if __name__=='__main__':unittest.main()