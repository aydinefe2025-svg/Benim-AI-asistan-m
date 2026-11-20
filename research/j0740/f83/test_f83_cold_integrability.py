import math,sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import f83_cold_integrability as F

class TestColdNumericalRebuild(unittest.TestCase):
    def test_exact_linear_E_P_stays_exact_enthalpy(self):
        P=np.array([1.,2.,4.,8.]);E=10.+2.*P;h0=.1
        dp=np.diff(P);de=np.diff(E);s=de/dp
        H=np.r_[h0,h0+np.cumsum(np.log1p((1+s)*dp/(E[:-1]+P[:-1]))/(1+s))]
        mu0=930.4;n=(E+P)/(mu0*F.MEV_TO_ERG*np.exp(H))
        src=np.column_stack([E/F.C**2,P,H*F.C**2,n])
        new,a=F.audit_and_rebuild(src)
        self.assertEqual(a['original_num_causal_enthalpy_interval_failures'],0)
        self.assertEqual(a['new_causal_bad_intervals'],0)
        self.assertLess(max(abs(new[:,2]/src[:,2]-1)),2e-14)
    def test_nonintegrable_h_even_if_n_rowwise_proportional_rejected_and_repaired(self):
        P=np.array([1.,2.,4.,8.]);E=10.+2*P;H=np.array([.1,.15,.16,.19]);n=(E+P)/(930.4*F.MEV_TO_ERG*np.exp(H))
        src=np.column_stack([E/F.C**2,P,H*F.C**2,n]);new,a=F.audit_and_rebuild(src)
        self.assertGreater(a['original_num_causal_enthalpy_interval_failures'],0)
        self.assertEqual(a['new_causal_bad_intervals'],0)
        self.assertEqual(a['new_monotone_bad_intervals'],0)
    def test_superluminal_segment_cannot_be_repaired_by_h_only(self):
        P=np.array([1.,2.,3.]);E=np.array([10.,10.5,12.]);H=np.array([.1,.15,.2]);n=(E+P)/(930.4*F.MEV_TO_ERG*np.exp(H))
        src=np.column_stack([E/F.C**2,P,H*F.C**2,n]);
        with self.assertRaisesRegex(ValueError,'SUPERLUMINAL'):F.audit_and_rebuild(src)
    def test_nonmonotone_energy_fails(self):
        a=np.array([[10.,1.,1.,1.],[9.,2.,2.,2.],[12.,3.,3.,3.]])
        with self.assertRaises(ValueError):F.audit_and_rebuild(a)
    def test_nonmonotone_baryon_density_fails(self):
        a=np.array([[10.,1.,1.,3.],[12.,2.,2.,2.],[14.,3.,3.,4.]])
        with self.assertRaises(ValueError):F.audit_and_rebuild(a)
    def test_row_mu0_drift_is_not_silent(self):
        P=np.array([1.,2.,4.]);E=10.+2*P;H=np.array([.1,.16,.21]);n=(E+P)/(930.4*F.MEV_TO_ERG*np.exp(H));n[-1]*=1.02
        src=np.column_stack([E/F.C**2,P,H*F.C**2,n])
        with self.assertRaisesRegex(ValueError,'MU0_IDENTITY'):F.audit_and_rebuild(src)
    def test_hash_drift_blocks_real_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fake.rns';p.write_text('1213\nnot original\n')
            with self.assertRaisesRegex(ValueError,'SHA_DRIFT'):F.locked_source(p)
    def test_source_original_exact_byte_p_e(self):
        a='3\n1.000000e+02 1.000000e+03 1 1\n2.000000e+02 2.000000e+03 2 2\n3.000000e+02 3.000000e+03 3 3\n';rows=[z.split() for z in a.splitlines()[1:]]
        self.assertEqual([' '.join(z[:2]) for z in rows],['1.000000e+02 1.000000e+03','2.000000e+02 2.000000e+03','3.000000e+02 3.000000e+03'])
    def test_physical_labels_remain_not_established(self):
        self.assertEqual(F.SCHEMA,'F83_REAL_F80_RNS_P_E_H_FIRSTLAW_PIECEWISE_CAUSAL_RECONSTRUCTION_V1')

if __name__=='__main__':unittest.main()

class TestOriginalPhysicalSource(unittest.TestCase):
    def test_original_1213_source_exact_bad_and_repaired(self):
        p=Path(__file__).parent/'F82_source_locked_BPS_MPA1.rns'
        if not p.is_file():self.skipTest('CI must copy the original source to this path before testing')
        raw,x,t=F.locked_source(p)
        self.assertEqual(F.sha(raw),F.EOS_SHA)
        new,report=F.audit_and_rebuild(x)
        self.assertEqual(report['original_num_causal_enthalpy_interval_failures'],11)
        self.assertEqual(report['original_num_monotone_enthalpy_interval_failures'],8)
        self.assertEqual(report['new_causal_bad_intervals'],0)
        self.assertEqual(report['new_monotone_bad_intervals'],0)
        self.assertLess(report['max_relative_n_change'],0.0001)
        self.assertTrue(np.array_equal(x[:,:2],new[:,:2]))
