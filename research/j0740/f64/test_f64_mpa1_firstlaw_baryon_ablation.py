import unittest,tempfile,subprocess,sys,math,os
from pathlib import Path
import numpy as np
from f64_mpa1_firstlaw_baryon_ablation import (integrate_baryons,load_rns_table,
 SOURCE_RNS_SHA,patch_C_output,C_OLD_FMT,C_OLD_ARGS,C_NEW_FMT,C_NEW_ARGS,parse_C,
 SOURCE_CENTER,C,write_rns)
SOURCE=Path(os.environ.get('F64_SOURCE','research/j0740/f63/MPA1_F63_sourceoriginal_196knots.rns'))
class F64Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.source=load_rns_table(SOURCE)
    def test_source_exact_pinned(self):
        import hashlib
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),SOURCE_RNS_SHA)
    def test_all_196_source_nodes_strict(self):
        self.assertEqual(self.source.shape,(196,4))
        self.assertTrue(np.all(np.diff(self.source,axis=0)>0))
    def test_source_n_per_rho_constant_proxy(self):
        nbyrho=self.source[:,3]/self.source[:,0]
        self.assertLess(np.max(nbyrho)/np.min(nbyrho)-1,2e-12)
    def test_firstlaw_n_monotone(self):
        n,h,dev=integrate_baryons(self.source)
        self.assertTrue(np.all(np.diff(n)>0))
        self.assertAlmostEqual(float(dev[0]),0.,places=13)
    def test_firstlaw_gauss_convergence_three_orders(self):
        a,*_=integrate_baryons(self.source,32)
        b,*_=integrate_baryons(self.source,64)
        c,*_=integrate_baryons(self.source,128)
        self.assertLess(np.max(abs(a/b-1)),2e-12)
        self.assertLess(np.max(abs(c/b-1)),2e-12)
    def test_direct_firstlaw_identity_for_linear_e_of_p(self):
        p=np.geomspace(1e30,1e34,12)
        e=p*100
        rho=e/(C*C)
        n=(p/p[0])**(100/101.)*1e33
        a=np.stack([rho,p,np.geomspace(1e17,1e19,len(p)),n],axis=1)
        z,_,dev=integrate_baryons(a)
        self.assertLess(np.max(abs(z/n-1)),2e-12)
    def test_n_mismatch_anchored_F63_center_nonzero(self):
        _,_,dev=integrate_baryons(self.source)
        x=float(np.interp(np.log(SOURCE_CENTER),np.log(self.source[:,0]),dev))
        self.assertTrue(.13<x<.15)
    def test_proxy_terminal_residual_bigger_than_center(self):
        _,_,dev=integrate_baryons(self.source)
        self.assertTrue(.50<dev[-1]<.60)
    def test_only_density_column_changed(self):
        n,_,_=integrate_baryons(self.source)
        y=self.source.copy();y[:,3]=n
        self.assertTrue(np.array_equal(y[:,:3],self.source[:,:3]))
        self.assertFalse(np.array_equal(y[:,3],self.source[:,3]))
    def test_RNS_C_diagnostic_exact_unique(self):
        src='abc\n'+C_OLD_FMT+'\n'+C_OLD_ARGS+'\n'
        new=patch_C_output(src)
        self.assertIn(C_NEW_FMT,new);self.assertIn(C_NEW_ARGS,new)
        self.assertNotIn(C_OLD_FMT,new)
    def test_fail_closed_C_signature_drift(self):
        with self.assertRaisesRegex(ValueError,'PRINTF_DRIFT'):patch_C_output('other source')
    def test_parse_six_values_not_four(self):
        p=parse_C('e_c header\n1.01536 2.073 12.533 346.61 2.4 6.104e48\n')
        self.assertEqual(p['mass_msun'],2.073)
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):parse_C('1.015 2.073 12.53 346\n')
    def test_unphysical_input_rejected(self):
        x=self.source.copy();x[18,1]=0
        with self.assertRaisesRegex(ValueError,'NONMONOTONE_ROWS'):integrate_baryons(x)
    def test_write_rebuild_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as q:
            p=Path(q)/'eos.rns';write_rns(p,self.source)
            self.assertEqual(np.loadtxt(p,skiprows=1).shape,(196,4))
if __name__=='__main__':unittest.main()