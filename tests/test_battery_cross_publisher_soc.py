"""Real 17-cell external source, 51-pair each: no fabricated lab labels."""
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "battery_curve_audit"))
import cross_publisher_soc_benchmark as b


class IndependentPublisherSocValidation(unittest.TestCase):
    def setUp(self):
        self.cells = b.load_fixture()

    def test_real_upstream_blob_integrity_all_17(self):
        self.assertEqual(len(self.cells), 17)
        self.assertEqual(sum(len(c) for _, c in self.cells), 867)
        self.assertTrue(all(len(c) == 51 and c[0][0] == 1 and c[-1][0] == 0
                            for _, c in self.cells))

    def test_real_distinct_physical_cells_and_benchmark(self):
        r = b.benchmark()
        self.assertEqual(r["distinct_physical_cell_comparisons"], 136)
        self.assertEqual(r["observed_alerts_across_distinct_cells"], 0)
        self.assertGreater(r["minimum_distinct_pair_rmse_mV"], 10)
        self.assertLess(r["minimum_distinct_pair_rmse_mV"], 11)
        self.assertEqual(r["controlled_related_pairs"], 51)
        self.assertEqual(r["detected_controlled_related_pairs"], 51)
        self.assertEqual(r["controlled_misses"], 0)
        self.assertEqual(r["release_decision"], "CROSS_PUBLISHER_SOC_SCREEN_PASS")
        self.assertFalse(r["axis_contract"]["compatible_with_customer_time_screen"])

    def test_controlled_related_examples_each_real_cell(self):
        for name, c in self.cells:
            with self.subTest(cell=name):
                ctrls = b.test_controls(c)
                self.assertEqual([label for label, _ in ctrls],
                                 ["exact", "decimal_alias", "injected_plus_1mV"])
                self.assertTrue(all(b.screen_pair(c, data) for _, data in ctrls))
                self.assertEqual(c, ctrls[0][1])
                self.assertEqual(c, ctrls[1][1])
                self.assertNotEqual(c, ctrls[2][1])

    def test_three_millivolt_control_outside_conservative_threshold(self):
        a = self.cells[0][1]
        shifted = tuple((x, v + Decimal("0.003")) for x, v in a)
        self.assertFalse(b.screen_pair(a, shifted))
        with self.assertRaisesRegex(ValueError, "threshold"):
            b.screen_pair(a, shifted, threshold_mv=20)

    def test_soc_axis_must_never_be_treated_as_time(self):
        c = self.cells[0][1]
        bad = tuple((x + Decimal("0.001"), v) for x, v in c)
        with self.assertRaisesRegex(ValueError, "coordinates"):
            b.rmse_mv(c, bad)

    def test_fixture_axis_tampering_fails_closed(self):
        fixture = json.loads(b.FIXTURE.read_text(encoding="utf-8"))
        fixture["x_axis_is_time"] = True
        self.assert_invalid_fixture(fixture, "axis")

    def test_source_raw_blob_tampering_fails_closed(self):
        fixture = json.loads(b.FIXTURE.read_text(encoding="utf-8"))
        fixture["records"][0]["raw_text"] = fixture["records"][0]["raw_text"].replace(
            "4.162", "4.163", 1)
        self.assert_invalid_fixture(fixture, "blob")

    def test_missing_physical_cell_fails_closed(self):
        fixture = json.loads(b.FIXTURE.read_text(encoding="utf-8"))
        fixture["records"].pop()
        self.assert_invalid_fixture(fixture, "17")

    def test_unphysical_grid_even_if_rehashed_fails_closed(self):
        fixture = json.loads(b.FIXTURE.read_text(encoding="utf-8"))
        first = fixture["records"][0]
        first["raw_text"] = first["raw_text"].replace("1.000 4.162", "2.000 4.162", 1)
        first["git_blob_sha1"] = b.git_blob_sha1(first["raw_text"].encode())
        self.assert_invalid_fixture(fixture, "SOC")

    def test_duplicate_cell_path_even_if_blob_valid_fails_closed(self):
        fixture = json.loads(b.FIXTURE.read_text(encoding="utf-8"))
        fixture["records"][1] = copy.deepcopy(fixture["records"][0])
        self.assert_invalid_fixture(fixture, "duplicate")

    def test_invalid_numeric_value_rejected_even_if_rehashed(self):
        fixture = json.loads(b.FIXTURE.read_text(encoding="utf-8"))
        first = fixture["records"][0]
        first["raw_text"] = first["raw_text"].replace("1.000 4.162", "1.000 NaN", 1)
        first["git_blob_sha1"] = b.git_blob_sha1(first["raw_text"].encode())
        self.assert_invalid_fixture(fixture, "invalid")

    def assert_invalid_fixture(self, fixture, expected):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "changed.json"
            p.write_text(json.dumps(fixture), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, expected):
                b.load_fixture(p)


if __name__ == "__main__":
    unittest.main()
