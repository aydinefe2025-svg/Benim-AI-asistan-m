"""Fractional passive series term source physics, nested specimen selection and guards."""
import math,unittest
from research.battery_curve_audit import graz_eis_fractional_inductive_repair as m
try:import numpy as np
except ImportError:np=None


def synthetic_source(alpha=.9):
    f=[10**(5-.07*i) for i in range(101)]
    z=[0.004+0.015*(1j*hz/100000)**alpha+0.004/(1+1j*2*math.pi*hz*.03) for hz in f]
    return [(hz,abs(v),math.degrees(math.atan2(v.imag,v.real))) for hz,v in zip(f,z)]

class FractionalCircuit(unittest.TestCase):
    def test_source_shape(self):self.assertEqual(len(m.validate_spectrum(synthetic_source())),101)
    def test_nonmonotonic_original_frequency_rejected(self):
        x=synthetic_source();x[2]=x[1]
        with self.assertRaises(ValueError):m.validate_spectrum(x)
    def test_zero_magnitude_rejected(self):
        x=synthetic_source();x[2]=(x[2][0],0,x[2][2])
        with self.assertRaises(ValueError):m.validate_spectrum(x)
    def test_nonfinite_source_rejected(self):
        x=synthetic_source();x[2]=(x[2][0],float('nan'),x[2][2])
        with self.assertRaises(ValueError):m.validate_spectrum(x)
    def test_alpha_selection_excludes_heldout_physical_cell(self):
        d={}
        for i in range(10):
            for stage in m.LEVELS:
                d[(f'C{i:02}',stage)]={a:{'middle_band':1. if a==.91 else 9.} for a in m.CANDIDATE_ALPHAS}
        self.assertEqual(m.select_alpha_without_test_cell(d,'C00'),.91)
        for stage in m.LEVELS:
            d[('C00',stage)]={a:{'middle_band':0. if a==.94 else 100.} for a in m.CANDIDATE_ALPHAS}
        self.assertEqual(m.select_alpha_without_test_cell(d,'C00'),.91)
    @unittest.skipUnless(np is not None,'numpy/scipy installed in original-source scientific CI')
    def test_true_synthetic_fractional_recovered_on_blind_parity(self):
        self.assertLess(m.heldout(synthetic_source(),.9,'parity'),1.5)
    @unittest.skipUnless(np is not None,'numpy/scipy installed in original-source scientific CI')
    def test_true_synthetic_fractional_recovered_on_block(self):
        self.assertLess(m.heldout(synthetic_source(),.9,'middle_band'),4)
    @unittest.skipUnless(np is not None,'numpy/scipy installed in original-source scientific CI')
    def test_ideal_l_fails_on_true_fractional_synthetic(self):
        self.assertGreater(m.heldout(synthetic_source(),1,'parity'),5)
    @unittest.skipUnless(np is not None,'numpy/scipy installed in original-source scientific CI')
    def test_nonphysical_alpha_rejected(self):
        with self.assertRaises(ValueError):m.heldout(synthetic_source(),.3,'parity')
    def test_unknown_holdout_rejected(self):
        with self.assertRaises(ValueError):m.heldout(synthetic_source(),.9,'fake')

if __name__=='__main__':unittest.main()