"""External-source test contracts; artificial inputs are labeled synthetic.
Real published source retrieval is separately required in CI.
"""
import unittest
from research.battery_curve_audit.oxford_external_benchmark import parse_profile, audit_profiles


def synthetic(voltage_bias=0.0, size=120):
    rows = ["profile time,current,voltage"]
    for i in range(size):
        v = 3.55 + (i/119)*0.11 + voltage_bias
        rows.append(f"{i*5},{2.0},{v:.9f}")
    return ("\n".join(rows) + "\n").encode()


class OxfordTimeVoltageContracts(unittest.TestCase):
    def test_numeric_profile_time_and_voltage_are_read_without_index_swap(self):
        t,v = parse_profile(synthetic())
        self.assertEqual(len(t), 120)
        self.assertEqual((t[0],t[-1]), (0.0, 595.0))
        self.assertAlmostEqual(v[0],3.55)
        self.assertAlmostEqual(v[-1],3.66)

    def test_incomplete_or_soc_only_csv_fails_closed(self):
        for raw in (b"soc,voltage\n0,3.0\n", b"time,current\n0,3.2\n", b""):
            with self.subTest(raw=raw[:25]), self.assertRaises(ValueError):
                parse_profile(raw)

    def test_time_regression_rejected_without_automatic_sorting(self):
        raw = synthetic().replace(b"10,2.0",b"0,2.0",1)
        with self.assertRaisesRegex(ValueError,"time"):
            parse_profile(raw)

    def test_nan_voltage_rejected_without_filling(self):
        raw = synthetic().replace(b"3.550000000",b"nan",1)
        with self.assertRaises(ValueError):
            parse_profile(raw)

    def test_missing_cell_not_a_false_independent_screen(self):
        with self.assertRaises(ValueError):
            audit_profiles({"BMP_cell1":synthetic()})

    def test_real_voltage_axis_with_controlled_clone_is_detected(self):
        out = audit_profiles({
            "BMP_cell1": synthetic(0),
            "BMP_cell2": synthetic(0.04),
        })
        self.assertTrue(out["controlled_1mv_clone_detected"])
        self.assertFalse(out["controlled_10mv_clone_detected"])
        self.assertFalse(out["source_pair_near_candidate"])
        self.assertEqual(out["time_unit"], "s")
        self.assertEqual(out["voltage_unit"], "V")
        self.assertEqual(out["cell_count"], 2)
        self.assertEqual(out["decision"], "SCREEN_ONLY_NOT_CERTIFIED")

    def test_identical_source_files_require_review(self):
        out = audit_profiles({"BMP_cell1":synthetic(),"BMP_cell2":synthetic()})
        self.assertEqual(out["decision"], "REVIEW_REQUIRED")
        self.assertTrue(out["source_bytes_identical"])


if __name__=="__main__":
    unittest.main()
