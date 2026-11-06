"""Focused artificial-EOS conversion checks, independent of full RNS pipeline."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
from jester_to_rns import from_jester_npz,write_rns,C,G

class TestJESTERtoRNS(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'test.npz'
        x=np.geomspace(1e-18,1e-9,240)
        e=2e-15*(x/x[0])**0.7
        n=1e39*(x/x[0])**0.66
        h=np.linspace(0.002,0.92,len(x))
        np.savez(self.path,n=n,p=x,e=e,h=h,masses_EOS=np.linspace(.5,2.5,50),radii_EOS=np.linspace(15,10,50))
    def tearDown(self):self.temp.cleanup()
    def test_physical_units_and_count(self):
        a,info=from_jester_npz(self.path,points=180)
        self.assertEqual(a.shape,(180,4))
        self.assertAlmostEqual(a[0,0],2e-15*C**2/G*1e-3,delta=2e-15*C**2/G*1e-5)
        self.assertAlmostEqual(a[0,1],1e-18*C**4/G*10,delta=1e-18*C**4/G*.00001)
        self.assertAlmostEqual(a[0,3],1e33,delta=1e20)
        self.assertAlmostEqual(a[0,2],1.0)
        self.assertTrue(np.all(np.diff(a,axis=0)>0))
    def test_max_200_points(self):
        with self.assertRaises(ValueError):from_jester_npz(self.path,points=210)
    def test_no_bad_EOS_movement(self):
        with np.load(self.path,allow_pickle=False) as x:
            data={k:np.array(x[k]) for k in x.files}
        data['p'][45]=data['p'][44]
        np.savez(self.path,**data)
        with self.assertRaisesRegex(ValueError,'pressure'):from_jester_npz(self.path)
    def test_write_and_read_four_columns(self):
        arr,_=from_jester_npz(self.path,points=100)
        dst=Path(self.temp.name)/'eosTest'
        write_rns(dst,arr)
        s=dst.read_text().splitlines()
        self.assertEqual(s[0],'100')
        self.assertEqual(np.loadtxt(dst,skiprows=1).shape,(100,4))

if __name__=='__main__': unittest.main()
