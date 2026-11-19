import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_jester_bps_mpa1_rns as rns

class RNSExportTests(unittest.TestCase):
    def test_table_has_native_rns_columns_and_cold_firstlaw_density(self):
        p=Path(__file__).with_name("rns_export_test.tmp")
        meta=rns.export_rns_eos(p,n_grid=500,max_enthalpy=1.5)
        try:
            a=np.loadtxt(p,skiprows=1)
            count=int(p.read_text().splitlines()[0])
            self.assertEqual(count,meta["rows"])
            self.assertEqual(a.shape,(count,4))
            self.assertLessEqual(count,1950)
            self.assertTrue(np.all(np.isfinite(a)) and np.all(a>0))
            self.assertTrue(np.all(np.diff(a,axis=0)>0))
            H=a[:,2]/rns.CGS_C**2
            e_geom=a[:,0]*1e3*rns.G/rns.C**2
            p_geom=a[:,1]*rns.G/(10*rns.C**4)
            n_geom=a[:,3]*1e6
            n_law=(e_geom+p_geom)/(rns.MU0_GEOM*np.exp(H))
            self.assertLess(np.max(np.abs(n_geom/n_law-1)),2e-12)
            self.assertEqual(meta["firstlaw_absolute_mu_surface_MeV"],930.4)
            self.assertFalse(meta["source_native_n_used"])
        finally:
            if p.exists():p.unlink()

    def test_external_rns_provenance_is_pinned(self):
        self.assertEqual(rns.RNS_COMMIT,"97e85d325a33e37f702306414533f6cd77812477")

if __name__=="__main__": unittest.main(verbosity=2)

