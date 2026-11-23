import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f142_native_causality_origin import bracket_source,summarize_original_derived
class F142Tests(unittest.TestCase):
 def test_original_knot_secant_classification(self):
  p=np.array([1.,2.,3.,4.,5.]);e=np.array([10.,11.5,12.,14.,16.])
  self.assertTrue(bracket_source(p,e,1.5)['endpoint_secant_causal'])
  self.assertFalse(bracket_source(p,e,2.5)['endpoint_secant_causal'])
 def test_source_boundary_extrapolation_denied(self):
  with self.assertRaisesRegex(ValueError,'OUTSIDE_TABULATED_SOURCE'):
   bracket_source(np.arange(1.,6.),np.arange(1.,6.),6.)
 def test_native_and_source_not_conflated(self):
  p=np.arange(1.,7.);e=4*p;d=np.column_stack([p,e])
  original=np.array([.5,1.1,.8]);new=np.array([1.3,.8,.8])
  grid=np.array([1.5,2.5,3.5])
  result=summarize_original_derived('ENG',p,e,d,original,new,grid)
  self.assertEqual(result['derived_native_acausal_n'],1)
  self.assertEqual(result['original_native_acausal_at_derived_acausal_n'],0)
  self.assertEqual(result['original_source_endpoint_secant_acausal_at_derived_acausal_n'],0)
 def test_no_reproduced_violations_must_fail(self):
  p=np.arange(1.,7.);d=np.column_stack([p,4*p])
  with self.assertRaisesRegex(ValueError,'NOT_REPRODUCED'):
   summarize_original_derived('ENG',p,4*p,d,np.array([.5,.8]),np.array([.8,.7]),np.array([1.5,2.5]))
if __name__=='__main__':unittest.main()
