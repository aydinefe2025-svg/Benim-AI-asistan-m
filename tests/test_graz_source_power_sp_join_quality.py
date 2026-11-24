import unittest
from research.battery_curve_audit import graz_source_power_sp_join_quality as a

def r(t,device,p,line,flag=False):
    return (float(t),device,3.,1.,float(p),int(line),flag)

class OriginalPowerJoinGateTests(unittest.TestCase):
    def test_numeric_inconsistency_not_physical_calibration(self):
        self.assertTrue(a.inconsistent_power(3.,1.,0.))
        self.assertFalse(a.inconsistent_power(3.,0.,0.))
        self.assertFalse(a.inconsistent_power(3.,1.,3.))
        with self.assertRaises(ValueError):a.inconsistent_power(3.,float("nan"),3.)

    def test_quarantine_replaces_bad_source_record_or_loses_sp(self):
        e=[r(0,"COM3",3,2),r(1,"COM4",0,3,True),r(2,"COM3",3,4)]
        sp=[(1.1,10.,11.,12.),(100.,1.,2.,3.)]
        d=a.compare_file(e,sp,{3})
        self.assertEqual(d["before_matched_SP_rows"],1)
        self.assertEqual(d["before_mapped_to_quarantined_electrical_power_row"],1)
        self.assertEqual(d["after_matched_SP_rows"],1)
        self.assertEqual(d["changed_paired_source_electrical_line_after_quarantine"],1)
        self.assertEqual(d["unmatched_in_both"],1)

    def test_empty_good_rows_is_rejected(self):
        e=[r(0,"COM4",0,2,True)]
        with self.assertRaises(ValueError):
            a.compare_file(e,[(0.,1.,1.,1.)],{2})

    def test_conflicting_device_exact_tie_is_not_matched(self):
        e=[r(0,"COM3",3,2),r(1,"COM4",3,3)]
        match=a.nearest_source_line_ids(e,[(.5,1.,2.,3.)])
        self.assertEqual(match,[None])

    def test_no_fabricated_source(self):
        with self.assertRaises(Exception):a.inspect_original(b"not original source",100)

    def test_exact_source_populations(self):
        self.assertEqual(sum(a.EXPECTED_ELEC.values()),1091337)
        self.assertEqual(sum(a.EXPECTED_SP.values()),234021)
        self.assertEqual(sum(a.EXPECTED_QUARANTINED.values()),1900)

if __name__=="__main__":
    unittest.main()
