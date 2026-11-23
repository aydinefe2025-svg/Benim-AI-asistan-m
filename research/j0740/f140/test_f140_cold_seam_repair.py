"""F140 mathematical red/green regression (native acceptance lives in CI)."""
import sys,unittest,tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f140_cold_seam_repair import bridge_analytic,choose_native_seam,assemble_derived,write_lal_two_col,CONV
class TestF140(unittest.TestCase):
 def test_causal_continuous_bridge(self):
  b=bridge_analytic(1,2,100,105,3)
  self.assertAlmostEqual(b['cs2'],.2)
  self.assertEqual(b['e'][0],100);self.assertEqual(b['e'][-1],105)
  self.assertLess(np.max(np.abs(b['mu']/b['mu'][0]-np.exp(b['h']))),1e-11)
 def test_cold_differential_first_law(self):
  b=bridge_analytic(1,2,100,105,3)
  self.assertLess(np.max(np.abs((np.diff(b['e'])/np.diff(b['n']))/b['mu'][:-1]-1)),1e-4)
 def test_noncausal_endpoints_fail_closed(self):
  for e1 in (99.,100.1,101.):
   with self.assertRaisesRegex(ValueError,'ENDPOINT_CAUSAL_NO_GO'):bridge_analytic(1,2,100,e1,3)
 def test_original_knot_preservation(self):
  p=np.arange(1.,401.);e=10*p;e[254]=e[253]-5
  lo,hi=choose_native_seam(p,e);b=bridge_analytic(p[lo],p[hi],e[lo],e[hi],1)
  pp,ee=assemble_derived(p,e,lo,hi,b)
  self.assertTrue(np.all(np.diff(ee)>0));self.assertTrue(np.all(np.diff(pp)>0))
  self.assertTrue(np.array_equal(pp[:lo],p[:lo]))
  self.assertTrue(np.array_equal(pp[-(len(p)-hi-1):],p[hi+1:]))
 def test_reject_bad_source(self):
  with self.assertRaises(ValueError):choose_native_seam([1,2],[1])
 def test_lal_geometrized_round_trip_units(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'eos.txt'
   write_lal_two_col(np.array([1e-10,2e-10]),np.array([1e-8,2e-8]),f)
   a=np.loadtxt(f);self.assertAlmostEqual(a[0,0]/CONV,1e-10)
if __name__=='__main__':unittest.main()
