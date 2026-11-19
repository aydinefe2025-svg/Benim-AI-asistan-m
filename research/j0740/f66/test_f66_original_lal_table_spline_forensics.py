"""Fail-closed analytic and provenance tests for F66 raw-table spline trace."""
from pathlib import Path
import importlib.util,unittest,numpy as np
from scipy.interpolate import CubicSpline
S=Path(__file__).parent/'f66_original_lal_table_spline_forensics.py'
spec=importlib.util.spec_from_file_location('f66',S);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Test(unittest.TestCase):
 def setUp(self):
  self.raw=np.array([[1.,1.],[2.,4.],[3.,5.],[4.,5.1],[5.,12.],[6.,20.],[7.,23.],[8.,24.],[9.,30.],[10.,42.],[11.,55.],[12.,65.],[13.,80.],[14.,84.],[15.,102.],[16.,120.],[17.,132.],[18.,160.],[19.,182.],[20.,220.]])*np.array([1e-16,1e-13])
  self.p=np.linspace(self.raw[0,0]+.05e-16,self.raw[-1,0]-.05e-16,210)
 def test_raw_monotone(self):self.assertTrue(np.all(np.diff(self.raw,axis=0)>0))
 def test_source_rows_bad_path(self):
  with self.assertRaises(Exception):m.source_rows('/does/not/exist')
 def test_cubic_interpolator_natural_exact_knots(self):
  p=self.raw[:,0];e=self.raw[:,1]; cs=CubicSpline(p*1e15,e*1e13,bc_type='natural')
  self.assertLess(np.max(abs(cs(p*1e15)/1e13-e)),1e-23)
 def test_interp_finite(self):
  out=m.evaluate_interpolants(self.raw,self.p)
  self.assertTrue(all(np.isfinite(x).all() for x in out))
 def test_pchip_shape_preserving(self):
  self.assertGreaterEqual(m.evaluate_interpolants(self.raw,self.p)[3].min(),0)
 def test_cubic_reproduction_deterministic(self):
  a=m.evaluate_interpolants(self.raw,self.p);b=m.evaluate_interpolants(self.raw,self.p)
  self.assertTrue(all(np.array_equal(x,y) for x,y in zip(a,b)))
 def test_reject_extrapolation_low(self):
  with self.assertRaisesRegex(ValueError,'OUTSIDE'):m.evaluate_interpolants(self.raw,np.array([self.raw[0,0],self.raw[1,0]]))
 def test_reject_extrapolation_high(self):
  with self.assertRaisesRegex(ValueError,'OUTSIDE'):m.evaluate_interpolants(self.raw,np.array([self.raw[-2,0],self.raw[-1,0]]))
 def test_reject_unsorted_pressure(self):
  with self.assertRaisesRegex(ValueError,'OUTSIDE'):m.evaluate_interpolants(self.raw,np.array([self.p[1],self.p[0]]))
 def test_reject_source_less_than_two_columns(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   x=Path(d)/'bad.dat';x.write_text('1 2 3\n'*40)
   with self.assertRaisesRegex(ValueError,'TWO_COLUMN'):m.source_rows(x)
 def test_reject_source_decreasing_pressure(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   x=Path(d)/'bad.dat';x.write_text(''.join(f'{a} {b}\n' for a,b in self.raw[::-1]))
   with self.assertRaisesRegex(ValueError,'INVALID_RAW'):m.source_rows(x)
 def test_source_format_whitespace_comments(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   x=Path(d)/'tab.dat';x.write_text('# comment\n'+'\n'.join(f'{a:.17e}  {b:.17e}' for a,b in self.raw)+'\n');self.assertEqual(m.source_rows(x).shape,(20,2))
 def test_reject_bad_installed_root(self):
  with self.assertRaisesRegex(ValueError,'INVALID_INSTALLED_ROOT'):m.find_installed_sources(Path('/zzzz_does_not_exist'))
 def test_f65_hash_pinned(self):self.assertEqual(len(m.F65_SHA),64)
 def test_eos_model_is_original(self):self.assertEqual(set(m.EOS),set(['APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2']))
if __name__=='__main__':unittest.main()