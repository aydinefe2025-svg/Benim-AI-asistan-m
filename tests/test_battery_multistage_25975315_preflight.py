"""All test inputs are synthetic; publication access is tested in CI."""
import json
import unittest
from research.battery_curve_audit.multistage_25975315_preflight import (
    ARTICLE_ID, audit_article, parse_metadata, license_ok,
)
def fixture():
    return {
        "id": ARTICLE_ID, "doi": "10.6084/m9.figshare.25975315.v1",
        "license": {"name": "CC BY 4.0",
                    "url": "https://creativecommons.org/licenses/by/4.0/"},
        "files": [
            {"id": 1, "name": "stage_1.zip", "size": 9_000_000_000,
             "computed_md5": "a" * 32},
            {"id": 2, "name": "meta.csv", "size": 1200,
             "computed_md5": "b" * 32},
        ],
    }
class MultiCellPublisherGate(unittest.TestCase):
    def test_metadata_is_never_relabelled_physical_validation(self):
        d = audit_article(fixture())
        self.assertEqual(d["file_count_metadata"], 2)
        self.assertEqual(d["total_bytes_metadata"], 9_000_001_200)
        self.assertEqual(d["license_status"], "CC_BY_4_0_PUBLISHER_METADATA")
        self.assertEqual(d["verified_independent_physical_cells"], 0)
        self.assertEqual(d["original_files_downloaded"], 0)
        self.assertFalse(d["raw_time_axis_verified"])
        self.assertFalse(d["field_false_match_rate_calculated"])
        self.assertFalse(d["production_release_allowed"])
    def test_html_source_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_metadata(b"<html>403 forbidden</html>")
    def test_wrong_article_is_rejected(self):
        for key, value in [("id", 12), ("doi", "10.6084/m9.figshare.999")]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                f = fixture()
                f[key] = value
                audit_article(f)
    def test_commercial_license_cannot_be_assumed(self):
        for val in [
            None,
            {"name": "CC BY-NC 4.0",
             "url": "https://creativecommons.org/licenses/by-nc/4.0/"},
            {"name": "CC BY 4.0", "url": "https://example.net/by/4.0/"}
        ]:
            self.assertFalse(license_ok(val))
            f = fixture()
            f["license"] = val
            self.assertEqual(audit_article(f)["decision"], "SOURCE_LICENSE_REVIEW_REQUIRED")
    def test_invalid_member_metadata_is_rejected(self):
        for key, val in [("id", -1), ("id", True), ("size", -1),
                         ("size", 30_000_000_001), ("name", "../escape.zip")]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                f = fixture()
                f["files"][0][key] = val
                audit_article(f)
    def test_duplicate_file_id_is_rejected(self):
        f = fixture()
        f["files"][1]["id"] = f["files"][0]["id"]
        with self.assertRaises(ValueError):
            audit_article(f)
    def test_duplicate_names_flagged_not_treated_as_independent_cells(self):
        f = fixture()
        f["files"][1]["name"] = f["files"][0]["name"]
        d = audit_article(f)
        self.assertEqual(d["duplicate_file_names_metadata"], 1)
        self.assertEqual(d["decision"], "SOURCE_NAME_COLLISIONS_REVIEW_REQUIRED")
        self.assertEqual(d["verified_independent_physical_cells"], 0)
    def test_small_file_list_is_bounded_and_zip_is_not_downloaded(self):
        f = fixture()
        f["files"] += [
            {"id": 3 + i, "name": f"test_{i}.csv", "size": 100 + i,
             "computed_md5": "a" * 32} for i in range(100)
        ]
        d = audit_article(f)
        self.assertEqual(d["small_text_candidates_count"], 101)
        self.assertEqual(len(d["small_text_candidates_first_20"]), 20)
        self.assertEqual(d["original_files_downloaded"], 0)
    def test_live_metadata_receipt_is_not_a_measured_false_match_rate(self):
        d = audit_article(parse_metadata(json.dumps(fixture()).encode()))
        self.assertEqual(d["paper_reported_cells_not_checked"], 279)
        self.assertEqual(d["time_voltage_pairs_measured"], 0)
if __name__ == "__main__":
    unittest.main()
