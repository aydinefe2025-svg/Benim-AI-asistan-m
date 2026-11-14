import unittest
import numpy as np
from source_crust_cs2_audit import diagnose_arrays
class SourceCrustTests(unittest.TestCase):
 def sample(self):
  p=np.geomspace(1e-15,1e-9,100)
  e=np.geomspace(1e-13,1e-7,100)
  dlog=np.full(100,2.)
  cs2=p/(e*dlog)
  h=np.linspace(.1,1.,100)
  return p,e,cs2,dlog,h
 def test_identity_and_negative_at_native_knot(self):
  p,e,c,d,h=self.sample()
  d[9]=-2.;c[9]=p[9]/(e[9]*d[9])
  out=diagnose_arrays(p,e,c,d,h)
  self.assertTrue(out['source_analytic_identity_verified'])
  self.assertEqual(out['negative_native_cs2_count'],1)
  self.assertEqual(out['negative_native_cs2_nodes'][0]['index'],9)
  self.assertLess(out['negative_native_cs2_nodes'][0]['dloge_dlogp'],0)
 def test_inconsistent_source_values_refused(self):
  p,e,c,d,h=self.sample();c[9]*=-1
  with self.assertRaisesRegex(ValueError,'not consistent'):
   diagnose_arrays(p,e,c,d,h)
 def test_source_pressure_requires_increase(self):
  p,e,c,d,h=self.sample();p[10]=p[9]
  with self.assertRaisesRegex(ValueError,'Invalid'):
   diagnose_arrays(p,e,c,d,h)
 def test_nonmonotonic_energy_not_sorted_away(self):
  p,e,c,d,h=self.sample();e[12]=e[11]*.95;c=p/(e*d)
  out=diagnose_arrays(p,e,c,d,h)
  self.assertEqual(out['e_nonincreasing_edges'],1)
if __name__=='__main__':unittest.main()
