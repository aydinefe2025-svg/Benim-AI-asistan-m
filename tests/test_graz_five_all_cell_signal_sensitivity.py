"""No source fabricated: fixture checks only, real original is CI evidence."""
import unittest
from research.battery_curve_audit import graz_five_all_cell_signal_sensitivity as m


class FiveSourceSensitivity(unittest.TestCase):
    def test_three_threshold_monotonicity(self):
        e=[(float(t),"COM3",3.5,1.0) for t in range(12)]
        s=[(2.2,100.,200.,300.),(6.6,101.,201.,300.),(11.7,102.,202.,300.)]
        x=m.nearest_summary(e,s)
        self.assertEqual(list(x),["0.5","1.0","2.5"])
        self.assertEqual(x["0.5"]["matched_sp_rows"],2)
        self.assertEqual(x["1.0"]["matched_sp_rows"],3)
        self.assertEqual(x["2.5"]["matched_sp_rows"],3)
        self.assertEqual(x["0.5"]["matched_sp_rows"] + x["0.5"]["unmatched_sp_rows"],3)

    def test_conflicted_equal_distance_is_excluded(self):
        e=[(0.,"COM3",3.,1.),(1.,"COM4",3.,-1.)]
        s=[(.5,100.,200.,300.)]
        x=m.nearest_summary(e,s)
        self.assertEqual(x["2.5"]["matched_sp_rows"],0)
        self.assertEqual(x["2.5"]["ambiguous_device_conflict_ties"],1)

    def test_disjoint_sensor_is_not_forced_to_pair(self):
        e=[(float(t),"COM3",3.5,0.) for t in range(10)]
        s=[(100.0+5*t,10.,11.,12.) for t in range(4)]
        x=m.nearest_summary(e,s)
        self.assertTrue(all(q["matched_sp_rows"]==0 for q in x.values()))

    def test_no_unauthenticated_original_archive_accepted(self):
        with self.assertRaises(Exception):
            m.inspect(b"fake",4)

    def test_identifiers_and_scope_do_not_move_to_other_experiments(self):
        self.assertEqual(m.EXPECTED_CELLS,("01","02","03","04","05"))
        self.assertEqual(sum(m.EXPECTED_ELECTRICAL.values()),1091337)
        self.assertEqual(sum(m.EXPECTED_SP_COUNTS.values()),234021)
        self.assertEqual(m.TOLERANCES,(0.5,1.0,2.5))


if __name__=="__main__":
    unittest.main()
