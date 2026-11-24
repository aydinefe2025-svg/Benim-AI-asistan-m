import unittest
from research.battery_curve_audit.graz_com4_transition_audit import Row
from research.battery_curve_audit import graz_power_reconstruction as m

class ReconstructionTests(unittest.TestCase):
    def test_zero_power_is_not_overwritten(self):
        r=Row(2,0,'COM4',4.34,4.5,0)
        d=m.estimate(r)
        self.assertEqual(d['logged_power_numeric'],0)
        self.assertAlmostEqual(d['derived_vi_numeric'],19.53)
        self.assertFalse(d['independent_power_measurement'])
    def test_other_device_rejected(self):
        with self.assertRaises(ValueError):m.estimate(Row(2,0,'COM3',4.34,4.5,0))
    def test_nonzero_power_rejected(self):
        with self.assertRaises(ValueError):m.estimate(Row(2,0,'COM4',4.34,4.5,20))
    def test_missing_interval_excluded(self):
        rows=[Row(2,0,'COM4',4,4,0),Row(3,1,'COM4',4,4,0),Row(4,20,'COM4',4,4,0),Row(5,21,'COM4',4,4,0)]
        d=m.integrate(rows)
        self.assertEqual(d['covered_seconds'],2)
        self.assertEqual(d['excluded_long_gap_count'],1)
        self.assertAlmostEqual(d['derived_vi_hour_numeric'],32/3600)
    def test_nonflag_interrupts_integration(self):
        rows=[Row(2,0,'COM4',4,4,0),Row(3,1,'COM4',4,4,16),Row(4,2,'COM4',4,4,0)]
        self.assertEqual(m.integrate(rows)['covered_seconds'],0)
    def test_comparator_does_not_select_on_residual(self):
        rows=[Row(2,0,'COM4',4.34,4.5,20),Row(3,1,'COM4',4.34,4.5,200),Row(4,2,'COM4',4.34,4.5,0),Row(5,3,'COM3',4.34,4.5,20)]
        d=m.validate_comparators(rows)
        self.assertEqual(d['n'],2)
        self.assertEqual(d['within_5pct'],1)
    def test_invalid_numeric_rejected(self):
        with self.assertRaises(ValueError):m.estimate(Row(2,0,'COM4',float('nan'),4.5,0))
if __name__=='__main__':unittest.main()
