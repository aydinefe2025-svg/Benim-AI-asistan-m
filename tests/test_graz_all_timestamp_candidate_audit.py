import unittest
from research.battery_curve_audit import graz_all_timestamp_candidate_audit as a

def row(t,device,v,i,p,line):
    return (float(t),device,float(v),float(i),float(p),int(line),False)

class AllOriginalNearestCandidatesTests(unittest.TestCase):
    def test_bisect_left_misses_conflicting_same_timestamp_devices(self):
        e=[row(0,"COM3",3,1,3,2),
           row(0,"COM4",3,2,0,3),
           row(0,"COM3",3,1,3,4),
           row(1,"COM3",3,1,3,5)]
        sp=[(0.,1.,2.,3.)]
        old=a.previous.nearest_source_line_ids(e,sp)
        full=a.nearest_all_candidate_records(e,sp)
        self.assertEqual(old,[2])
        self.assertEqual(full[0]["status"],"ambiguous_distinct_source_readings")
        self.assertIsNone(full[0]["line"])
        r=a.compare_old_to_complete(e,sp)
        self.assertEqual(r["previously_accepted_pair_now_rejected"],1)

    def test_duplicate_same_value_not_proof_of_unique_original_line(self):
        e=[row(0,"COM3",3,1,3,2),row(0,"COM3",3,1,3,3),row(1,"COM3",3,1,3,4)]
        r=a.nearest_all_candidate_records(e,[(0.,1.,2.,3.)])
        self.assertEqual(r[0]["status"],"duplicate_identical_reading_row_id_not_unique")
        self.assertEqual(r[0]["line"],2)

    def test_equidistant_different_values_are_rejected(self):
        e=[row(0,"COM3",3,1,3,2),row(1,"COM4",3,2,6,3)]
        r=a.nearest_all_candidate_records(e,[(.5,1.,2.,3.)])
        self.assertEqual(r[0]["status"],"ambiguous_distinct_source_readings")

    def test_outside_recorder_window_does_not_match(self):
        e=[row(0,"COM3",3,1,3,2),row(1,"COM3",3,1,3,3)]
        r=a.nearest_all_candidate_records(e,[(999.,1.,2.,3.)])
        self.assertEqual(r[0]["status"],"out_of_range")

    def test_duplicate_groups_count_distinct_signatures(self):
        e=[row(0,"COM3",3,1,3,2),row(0,"COM4",3,2,6,3),
           row(1,"COM3",3,1,3,4),row(1,"COM3",3,1,3,5),
           row(2,"COM3",3,1,3,6)]
        d=a.duplicate_time_summary(e)
        self.assertEqual(d["duplicate_original_timestamp_groups"],2)
        self.assertEqual(d["time_groups_with_conflicting_device_or_values"],1)
        self.assertEqual(d["source_rows_in_duplicate_timestamp_groups"],4)

    def test_fake_original_archive_must_fail(self):
        with self.assertRaises(Exception):a.inspect_archive(b"fake",4)

    def test_real_population_bounds(self):
        self.assertEqual(sum(a.EXPECTED_ELEC.values()),1091337)
        self.assertEqual(sum(a.EXPECTED_SP.values()),234021)
if __name__=="__main__":unittest.main()
