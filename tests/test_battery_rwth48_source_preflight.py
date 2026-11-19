"""Synthetic metadata tests; GitHub runner performs separate real HTTP probe."""
import unittest
from research.battery_curve_audit.rwth48_source_preflight import (
    SOURCE_URL, safe_size, classify_probe, MAX_ARCHIVE_BYTES,
)


def classify(**kw):
    options=dict(status=206,content_type="application/zip",
                 content_length="256",content_range="bytes 0-255/180000000",
                 head=b"PK\x03\x04"+b"0"*252,final_url=SOURCE_URL)
    options.update(kw)
    return classify_probe(**options)


class RWTH48RealSourcePreflight(unittest.TestCase):
    def test_large_valid_range_decision_no_false_download_claim(self):
        result=classify()
        self.assertEqual(result["decision"],"LARGE_ARCHIVE_REQUIRE_PARTIAL_SOURCE_ACCESS")
        self.assertEqual(result["size_bytes"],180000000)
        self.assertTrue(result["range_verified"])

    def test_small_valid_range_only_feasible_not_measured(self):
        result=classify(content_range="bytes 0-255/9000000")
        self.assertEqual(result["decision"],"BOUNDED_ARCHIVE_FEASIBLE")
        self.assertEqual(result["size_bytes"],9000000)

    def test_ignored_range_always_blocks_auto_download(self):
        result=classify(status=200,content_length="99990000",content_range=None)
        self.assertEqual(result["decision"],"MANUAL_SOURCE_BUDGET_REVIEW")
        self.assertFalse(result["range_verified"])

    def test_redirect_outside_university_is_blocked(self):
        with self.assertRaisesRegex(ValueError,"redirect"):
            classify(final_url="https://example.org/file.zip")

    def test_bad_content_zip_and_status_block(self):
        with self.assertRaises(ValueError):
            classify(content_type="text/html")
        with self.assertRaises(ValueError):
            classify(head=b"<html>")
        with self.assertRaises(ValueError):
            classify(status=404)

    def test_corrupt_or_ambiguous_length_rejected(self):
        for content_range in ("bytes 0-255/*", "bytes 0-255/0", "bytes nonsense"):
            with self.subTest(content_range=content_range), self.assertRaises(ValueError):
                classify(content_range=content_range)
        self.assertIsNone(safe_size(None,None))

    def test_wrong_range_start_cannot_be_verified(self):
        with self.assertRaises(ValueError):
            classify(content_range="bytes 4-255/8000000")

    def test_boundary_maxsize_may_be_fetched_only_in_separate_authorized_step(self):
        result=classify(content_range=f"bytes 0-255/{MAX_ARCHIVE_BYTES}")
        self.assertEqual(result["decision"],"BOUNDED_ARCHIVE_FEASIBLE")


if __name__=="__main__":
    unittest.main()
