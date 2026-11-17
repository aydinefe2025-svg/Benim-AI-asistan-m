import unittest
import numpy as np
from apr4_precise_root_n_ablation import baryon_variants,MAVG_G,RNS_MB_G
class TestBaryonAb(
 unittest.TestCase):
 def test_only_n_column_changes_and_firstlaw_relation(self):
  e=np.array([2.,3.,5.]);p=np.array([.01,.2,.5]);h=np.array([.01,.04,.1])
  old=np.column_stack([e*123.,p*999.,h*100.,np.array([1.,2.,4.])])
  d=baryon_variants(old,e,p,h)
  for key in d:
   self.assertTrue(np.array_equal(d[key][:,:3],old[:,:3]))
   self.assertTrue(np.all(np.diff(d[key][:,3])>0))
  rat=(1+p/e)*np.exp(-h)
  np.testing.assert_allclose(d["firstlaw_mavg"][:,3],old[:,3]*rat,rtol=1e-14)
  np.testing.assert_allclose(d["firstlaw_rns_mb"][:,3]/d["firstlaw_mavg"][:,3],MAVG_G/RNS_MB_G,rtol=1e-14)
 def test_reject_nonmonotone_firstlaw_column(self):
  e=np.array([2.,3.,5.]);p=np.array([.01,.02,.03]);h=np.array([.01,.1,.8])
  old=np.column_stack([e,p,h,np.array([1.,2.,3.])])
  with self.assertRaisesRegex(ValueError,"non-monotonic"):
   baryon_variants(old,e,p,h)
if __name__=="__main__":unittest.main()
