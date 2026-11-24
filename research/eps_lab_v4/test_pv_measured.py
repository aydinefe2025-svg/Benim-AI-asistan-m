import unittest
import numpy as np
import pv_measured as m
class TestMeasured(unittest.TestCase):
 def test_root(self):
  p=[.8,1e-7,.05,100,.04];v=np.array([0,.1,.4,.6]);i=m.current(v,p);u=v+i*p[2];np.testing.assert_allclose(p[0]-p[1]*np.expm1(u/p[4])-u/p[3]-i,0,atol=1e-9)
 def test_split_no_leakage(self):
  a,b=m.split(np.arange(10),np.arange(10,0,-1));self.assertFalse(np.any(a&b));self.assertTrue(np.all(a|b));self.assertTrue(a[0] and a[-1])
 def test_invalid(self):
  with self.assertRaises(ValueError):m.validate([1]*10,[1]*10)
 def test_fit_synthetic(self):
  v=np.linspace(0,.65,26);i=m.current(v,[.8,1e-7,.05,100,.04]);r=m.audit(v,i);self.assertLess(r['model']['rmse_A'],1e-6)
 def test_sparse(self):
  v=np.linspace(0,.65,26);i=m.current(v,[.8,1e-7,.05,100,.04]);r=m.sparse_audit(v,i,8);self.assertEqual((r['train_n'],r['test_n']),(8,18));self.assertIn('pchip',r);self.assertLess(r['model']['rmse_A'],1e-6)
 def test_reject_small_training(self):
  with self.assertRaises(ValueError):m.sparse_audit(np.arange(10),np.arange(10,0,-1),7)
if __name__=='__main__':unittest.main()
