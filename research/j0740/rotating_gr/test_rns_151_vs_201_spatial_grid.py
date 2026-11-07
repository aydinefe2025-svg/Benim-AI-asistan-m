import unittest
from rns_151_vs_201_spatial_grid import compare,audit

def star(m=2.073,r=12.53,rho=1.0e15,grid='201x401'):
 return {'mass_msun':m,'radius_eq_km':r,'central_energy_density_g_cm3':rho,
         'spin_hz_reported':346.5,'raw_stdout_tail':'MDIVxSDIV='+grid}
class SpatialMeshTests(unittest.TestCase):
 def test_strict_same_center_small_variations_pass(self):
  x=compare(star(grid='151x301'),star(2.075,12.56),'rotating')
  self.assertTrue(x['screen_pass'])
 def test_grid_identity_verified(self):
  with self.assertRaisesRegex(ValueError,'not documented'):
   compare(star(),star(grid='151x301'),'static')
 def test_material_radius_drift_rejected(self):
  x=compare(star(),star(2.075,12.83),'static')
  self.assertFalse(x['screen_pass'])
 def test_material_mass_drift_rejected(self):
  x=compare(star(),star(2.15,12.53),'rotating')
  self.assertFalse(x['screen_pass'])
 def test_wrong_center_density_rejected(self):
  with self.assertRaisesRegex(ValueError,'density'):
   compare(star(),star(rho=1.2e15),'rotating')
 def test_incomplete_model_fails(self):
  with self.assertRaisesRegex(ValueError,'missing'):
   compare({'mass_msun':2.0},star(),'rotating')
 def test_partial_source_refused(self):
  with self.assertRaisesRegex(ValueError,'identity'):
   audit({'status':'PARTIAL_NOT_FINAL'},None,None,None)
if __name__=='__main__':unittest.main()
