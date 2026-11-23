import sys,tempfile,unittest,json,hashlib
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f141_real_static_tov import verify_f140,choose_central_pressure,compare_convergence
class TestF141(unittest.TestCase):
 def test_pressure_from_energy(self):
  a=np.array([[float(i),10.*i] for i in range(1,400)])
  # target is mass-density converted to geom epsilon
  rho=1500*299792458.**2/(1000*6.67430e-11)
  p,e=choose_central_pressure(a,rho)
  self.assertAlmostEqual(p,150.)
 def test_tov_two_tolerance_requires_close_mass_radius(self):
  a={'radius_km':12.,'mass_msun':2.}
  self.assertTrue(compare_convergence(a,dict(a))['pass_two_tolerances'])
  with self.assertRaisesRegex(ValueError,'NONCONVERGENCE'):
   compare_convergence(a,{'radius_km':10.,'mass_msun':2.})
 def test_original_artifact_missing_fails(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaisesRegex(ValueError,'F140_REAL_ARTIFACT_MISSING'):verify_f140(d)
 def test_central_density_cannot_extrapolate(self):
  a=np.array([[float(i),10.*i] for i in range(1,400)])
  with self.assertRaisesRegex(ValueError,'OUTSIDE_SOURCE_E_RANGE'):
   choose_central_pressure(a,1e-100)
if __name__=='__main__':unittest.main()
