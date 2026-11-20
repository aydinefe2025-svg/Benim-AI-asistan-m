import unittest,sys,hashlib,tempfile,pathlib,json,os
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from f88_unified_apr_rns_input import create,RNS_SURFACE_RHO_CGS,RNS_SURFACE_P_CGS
R=Path(os.environ.get('F88_SOURCE_ROOT','/mnt/data/f87/actual'))
class OriginalRNSInputChecks(unittest.TestCase):
 def test_origin_and_original_rows(self):
  with tempfile.TemporaryDirectory() as t:
   meta=create(R,Path(t)/'m.rns',Path(t)/'meta.json')
   self.assertEqual(meta['original_native_rows_not_modified'],1833)
   self.assertEqual(meta['rns_rows'],1933)
   self.assertEqual(meta['original_source_nodes_cs2_gt1'],24)
   self.assertEqual(meta['status'],'RNS_INPUT_PREPARED_NOT_YET_C_EINSTEIN_STAR')
 def test_original_publisher_checksum(self):
  self.assertEqual(hashlib.sha256((R/'F87_verified_publisher_original.zip').read_bytes()).hexdigest(),'8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12')
 def test_original_native_rns_columns_exact_P_eps_n(self):
  with tempfile.TemporaryDirectory() as t:
   meta=create(R,Path(t)/'m.rns',Path(t)/'meta.json')
   f=np.loadtxt(Path(t)/'m.rns',skiprows=1)
   n=np.loadtxt(R/'eos.nb',skiprows=2)
   q=np.loadtxt(R/'eos.thermo',skiprows=1)
   from f88_unified_apr_rns_input import ONE_MEVFM3,C
   np.testing.assert_allclose(f[100:,0],n*939.56533*(1+q[:,9])*ONE_MEVFM3/C**2,rtol=1e-15)
   np.testing.assert_allclose(f[100:,1],n*q[:,3]*ONE_MEVFM3,rtol=1e-15)
   np.testing.assert_allclose(f[100:,3],n*1e39,rtol=1e-15)
 def test_extended_surface_below_native_RNS_boundary(self):
  with tempfile.TemporaryDirectory() as t:
   meta=create(R,Path(t)/'m.rns',Path(t)/'meta.json')
   rows=np.loadtxt(Path(t)/'m.rns',skiprows=1)
   self.assertLess(rows[0,0],RNS_SURFACE_RHO_CGS)
   self.assertLess(rows[0,1],RNS_SURFACE_P_CGS)
   self.assertTrue(np.all(np.diff(rows,axis=0)>0))
 def test_modified_original_source_hard_fail(self):
  with tempfile.TemporaryDirectory() as t:
   from shutil import copy2
   for n in ('F87_verified_publisher_original.zip','eos.nb','eos.thermo','eos.mr'):
    copy2(R/n,Path(t)/n)
   p=Path(t)/'eos.thermo';p.write_bytes(p.read_bytes()+b'# malicious')
   with self.assertRaises(AssertionError):create(Path(t),Path(t)/'out.rns',Path(t)/'meta.json')
if __name__=='__main__':unittest.main()
