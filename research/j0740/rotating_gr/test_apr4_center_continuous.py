import unittest
import numpy as np
import tempfile
from pathlib import Path
from apr4_center_continuous import audit_continuous, audit_pinned_npz, SourceInvalid

class ContinuousCausality(unittest.TestCase):
    def test_stable_log_powerlaw_stays_causal(self):
        p=np.geomspace(1e-4,1e-2,20)
        e=p**.7
        cs2=p/(.7*e)
        o=audit_continuous(p,e,cs2,center_e=float(e[13]))
        self.assertEqual(o['interpolant_status'],'PASS_CANDIDATE_BETWEEN_KNOT_SCREEN')
        self.assertTrue(0 < o['pchip_center_truncated_cs2_max'] < 1)
        self.assertEqual(o['intervals_reaching_center'],13)
        self.assertAlmostEqual(o['p_center'],float(p[13]),delta=float(p[13])*1e-9)
    def test_superluminal_log_powerlaw_is_caught(self):
        p=np.geomspace(1,4,20);e=0.5*p**.4;cs2=p/(.4*e)
        o=audit_continuous(p,e,cs2,center_e=float(e[13]))
        self.assertEqual(o['interpolant_status'],'FAIL_CANDIDATE_CAUSALITY')
        self.assertGreater(o['pchip_center_truncated_cs2_max'],1)
    def test_nonmonotonic_source_fails_closed(self):
        p=np.geomspace(1,4,6);e=np.array([1,1.2,1.3,1.29,1.8,2.]);cs2=np.ones(6)*.5
        with self.assertRaises(SourceInvalid):audit_continuous(p,e,cs2,center_e=1.6)
    def test_rejects_bad_center(self):
        p=np.geomspace(1,4,6);e=np.geomspace(2,8,6);cs2=np.ones(6)*.5
        with self.assertRaises(SourceInvalid):audit_continuous(p,e,cs2,center_e=20)
    def test_rejects_nonfinite_native(self):
        p=np.geomspace(1,4,6);e=np.geomspace(2,8,6);cs2=np.ones(6)*.5;cs2[-1]=np.nan
        with self.assertRaises(SourceInvalid):audit_continuous(p,e,cs2,center_e=4)
    def test_pinned_source_wrong_hash_cannot_be_used(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'APR4_EPP.npz'
            np.savez(p,p=np.array([1.,2.,3.,4.]),e=np.array([3.,4.,5.,6.]),cs2=np.ones(4))
            with self.assertRaises(SourceInvalid):audit_pinned_npz(p,{'expected_source_sha256':'0'*64,'expected_source_rows':4,'center_rho_g_cm3':1e15})

if __name__=='__main__':unittest.main()
