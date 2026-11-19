import tempfile
import unittest
from pathlib import Path
import numpy as np
from f68_pchip_cold_rns import resample_rns_table

class TestF68Table(unittest.TestCase):
    def setUp(self):
        x=np.linspace(-80,-5,240)
        p=np.exp(x)
        e=1e8*np.exp(.55*(x-x[0]))
        h=np.linspace(0,.4,len(x))
        n=np.exp(np.linspace(0,.5,len(x)))
        self.a=np.c_[p,e,h,n]

    def test_01_both_pinned_grids_are_physical_and_monotone(self):
        for mesh in (151,196):
            out=resample_rns_table(self._write(),mesh)
            self.assertEqual(out.shape,(mesh,4))
            self.assertTrue(np.isfinite(out).all())
            self.assertTrue((out>0).all())
            self.assertTrue((np.diff(out,axis=0)>0).all())

    def test_02_zero_enthalpy_surface_maps_to_positive_rns_offset(self):
        out=resample_rns_table(self._write(),151)
        self.assertEqual(out[0,2],1.0)

    def test_03_reject_wrong_mesh(self):
        with self.assertRaisesRegex(ValueError,'MESH_MUST'):
            resample_rns_table(self._write(),150)

    def test_04_reject_nonmonotone_energy(self):
        a=self.a.copy();a[20,1]=a[19,1]/2
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.dat';np.savetxt(p,a)
            with self.assertRaisesRegex(ValueError,'MONOTONE'):
                resample_rns_table(p,151)

    def _write(self):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup)
        p=Path(d.name)/'f67.dat';np.savetxt(p,self.a)
        return p

if __name__=='__main__':unittest.main()
