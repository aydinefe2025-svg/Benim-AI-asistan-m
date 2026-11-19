import unittest
import numpy as np
from f67_mpa1_pchip_firstlaw_tov import ColdEOS, EOS_LABEL
from f68_mpa1_pchip_cold_rns import rns_rows, MODEL, MESHES

class TestF68RNSConversion(unittest.TestCase):
    def setUp(self):
        p=np.geomspace(1e-34,3e-9,102)
        e=1e-9*(p/2e-10)**0.62
        self.eos=ColdEOS(np.c_[p,e],subdivisions=12,quadrature=32)

    def test_model_is_separately_named(self):
        self.assertIn('EXPLORATORY',MODEL)
        self.assertIn('NOT_ORIGINAL',MODEL)
        self.assertNotEqual(MODEL,EOS_LABEL)

    def test_only_pinned_meshes_allowed(self):
        for n in MESHES:
            self.assertEqual(len(rns_rows(self.eos,n)),n)
        with self.assertRaisesRegex(ValueError,'UNPINNED'):
            rns_rows(self.eos,152)

    def test_all_rns_columns_positive_and_strictly_monotone(self):
        a=rns_rows(self.eos,151)
        self.assertTrue(np.isfinite(a).all())
        self.assertTrue((a>0).all())
        self.assertTrue((np.diff(a,axis=0)>0).all())

    def test_firstlaw_n_remains_dimensionless_and_monotone(self):
        a=rns_rows(self.eos,196)
        self.assertAlmostEqual(a[0,3],1.,places=10)
        self.assertGreater(a[-1,3],a[0,3])

if __name__=='__main__':unittest.main()
