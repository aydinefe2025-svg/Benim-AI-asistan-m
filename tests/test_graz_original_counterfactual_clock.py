"""Artificial shifts on synthetic timestamps are test fixtures, not source evidence."""
import unittest
from research.battery_curve_audit import graz_original_counterfactual_clock as m

class RealClockIdentifiabilityGateTests(unittest.TestCase):
    def test_clock_shift_can_leave_nearest_match_unchanged(self):
        elec=[(float(x),"COM3",3.3,15.) for x in range(0,60)]
        sp=[(float(x)+.2,100.+x,200.+x,300.) for x in (5,10,15,20,25,30)]
        a=m.match_counterfactual(elec,sp,0.0,0.5)
        b=m.match_counterfactual(elec,sp,3.0,0.5)
        self.assertEqual(a["time_only_matches"],len(sp))
        self.assertEqual(b["time_only_matches"],len(sp))
        self.assertTrue(b["these_shifts_are_not_observed_clock_offsets"])

    def test_disjoint_outside_window_does_not_gain_matches(self):
        elec=[(float(x),"COM3",3.4,15.) for x in range(0,60)]
        sp=[(1000.+float(x),10.,11.,12.) for x in range(100)]
        for shift in m.OFFSETS_S:
            self.assertEqual(m.match_counterfactual(elec,sp,shift,1.0)["time_only_matches"],0)

    def test_device_conflicted_tie_remains_unmatched(self):
        elec=[(0.0,"COM3",3.3,2.),(1.0,"COM4",3.3,-2.)]
        sp=[(.5,1.,2.,3.)]
        r=m.match_counterfactual(elec,sp,0.0,0.5)
        self.assertEqual(r["time_only_matches"],0)
        self.assertEqual(r["rejected_conflicting_device_ties"],1)

    def test_reject_unknown_shift_or_tolerance(self):
        e=[(float(x),"COM3",3.3,0.) for x in range(12)]
        sp=[(2.0,1.,2.,3.)]
        with self.assertRaises(ValueError):
            m.match_counterfactual(e,sp,9.0,1.0)
        with self.assertRaises(ValueError):
            m.match_counterfactual(e,sp,0.0,3.0)

    def test_only_pinned_real_study_and_five_cells(self):
        self.assertEqual(m.CELLS,("01","02","03","04","05"))
        self.assertEqual(sum(m.ORIGINAL_ELECTRICAL_COUNTS.values()),1091337)
        self.assertEqual(sum(m.ORIGINAL_SP_COUNTS.values()),234021)
        with self.assertRaises(Exception):
            m.inspect_original(b"fabricated",1234)
