"""Graz real EIS vector-shift tests: synthetic math fixtures, physical source CI separate."""
import math
import unittest
from research.battery_curve_audit import graz_eis_2026_same_cell_delta as d

class ComplexEISPhysicsMath(unittest.TestCase):
    def test_phase_only_change_not_hidden_by_identical_magnitude(self):
        a=(10.0,0.01,-45.0)
        b=(10.0,0.01,-30.0)
        self.assertGreater(d.complex_shift_pct(a,b),25.0)
        self.assertEqual(d.abs_magnitude_shift_pct(a,b),0.0)
    def test_complex_shift_always_at_least_magnitude_shift(self):
        a=(10.0,0.01,-35.0)
        b=(10.0,0.011,-20.0)
        self.assertGreaterEqual(d.complex_shift_pct(a,b),d.abs_magnitude_shift_pct(a,b)-1e-10)
    def test_phase_wrap_179_vs_minus_179_does_not_create_fake_jump(self):
        a=(10.0,1.0,179.0)
        b=(10.0,1.0,-179.0)
        self.assertAlmostEqual(d.complex_shift_pct(a,b),2*math.sin(math.radians(1))*100,places=10)
    def test_same_measurement_zero(self):
        a=(10.0,0.003,-50.0)
        self.assertAlmostEqual(d.complex_shift_pct(a,a),0.0,places=10)
    def test_real_imag_convention(self):
        zr,minus_zi=d.cartesian_nyquist((10.0,2.0,-30.0))
        self.assertAlmostEqual(zr,math.sqrt(3),places=10)
        self.assertAlmostEqual(minus_zi,1.0,places=10)
    def test_reject_different_source_frequencies(self):
        with self.assertRaises(ValueError):
            d.complex_shift_pct((10.0,2.0,0.0),(11.0,2.0,0.0))
    def test_reject_zero_baseline_magnitude(self):
        with self.assertRaises(ValueError):
            d.complex_shift_pct((10.0,0.0,0.0),(10.0,0.1,0.0))
    def test_reject_nonfinite_phase(self):
        with self.assertRaises(ValueError):
            d.complex_shift_pct((10.0,0.2,float('nan')),(10.0,0.3,0.0))
    def test_percent_10pct_same_phase(self):
        self.assertAlmostEqual(d.complex_shift_pct((10.0,1.0,-45.0),(10.0,1.1,-45.0)),10.0,places=10)
    def test_not_capacity_and_no_absolute_safety_label(self):
        self.assertFalse(hasattr(d,'estimate_capacity_from_eis'))
        self.assertFalse(hasattr(d,'certify_mechanical_safety'))

if __name__=="__main__":unittest.main()
