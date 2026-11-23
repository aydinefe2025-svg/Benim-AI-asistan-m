import unittest
from research.battery_curve_audit import graz_source_pair_identity_audit as a

class IdentityAuditTests(unittest.TestCase):
    def test_aggregate_match_counts_can_hide_total_record_reassignment(self):
        e=[(float(i),"COM3",3.5,50.) for i in range(30)]
        sp=[(float(i)+0.15,100.,200.,300.) for i in range(4,20,5)]
        result=a.compare_record_identity(e,sp,3.)
        self.assertEqual(result["0_offset_matched_SP_rows"],len(sp))
        self.assertEqual(result["shifted_matched_SP_rows"],len(sp))
        self.assertEqual(result["matched_in_both_same_electrical_source_record_index"],0)
        self.assertEqual(result["matched_in_both_DIFFERENT_electrical_source_record_index"],len(sp))

    def test_time_outside_source_not_artificially_accepted(self):
        e=[(float(i),"COM3",3.5,0.) for i in range(25)]
        sp=[(float(i)+1000.,1.,2.,3.) for i in range(11)]
        for shift in a.SHIFTS:
            r=a.compare_record_identity(e,sp,shift)
            self.assertEqual(r["0_offset_matched_SP_rows"],0)
            self.assertEqual(r["shifted_matched_SP_rows"],0)

    def test_two_different_devices_equal_distance_remains_unassigned(self):
        e=[(0.,"COM3",3.,50.),(1.,"COM4",3.,-50.),(2.,"COM3",3.,50.),
           (3.,"COM4",3.,-50.),(4.,"COM3",3.,50.)]
        sp=[(.5,1.,2.,3.)]
        a0,ties=a.closest_event_indices(e,sp,0.)
        self.assertEqual(a0,[None])
        self.assertEqual(ties,1)

    def test_fail_closed_on_wrong_source_bytes(self):
        with self.assertRaises(Exception):a.inspect_original(b"FAKE_ZIP",10)

    def test_population_freeze(self):
        self.assertEqual(sum(a.ELECTRIC_EXPECTED.values()),1091337)
        self.assertEqual(sum(a.SP_EXPECTED.values()),234021)

if __name__=="__main__":
    unittest.main()
