"""Synthetic CSV fixtures only. CI independently verifies original publisher bytes."""
import hashlib
import unittest
from research.battery_curve_audit.figshare25975315_small_csv import (
    CSV_FILE_ID, CSV_EXPECTED_BYTES, locate_publisher_file, inspect_original_csv
)

def meta():
    return {"id":25975315,"doi":"10.6084/m9.figshare.25975315.v1",
            "license":{"name":"CC BY 4.0",
                       "url":"https://creativecommons.org/licenses/by/4.0/"},
            "files":[{"id":CSV_FILE_ID,"size":CSV_EXPECTED_BYTES,
                      "name":"experiments_meta.csv","computed_md5":"b"*32}]}

def pub(raw):
    return {"file_bytes":len(raw),"publisher_md5":hashlib.md5(raw).hexdigest()}


class OriginalPublisherCSVGate(unittest.TestCase):
    def test_article_pins_exact_original_file_identity(self):
        d=locate_publisher_file(meta())
        self.assertEqual(d["file_id"],CSV_FILE_ID)
        self.assertEqual(d["file_bytes"],30658)

    def test_changed_source_size_is_refused(self):
        m=meta()
        m["files"][0]["size"]+=1
        with self.assertRaisesRegex(ValueError,"size"):
            locate_publisher_file(m)

    def test_missing_original_file_is_refused(self):
        m=meta()
        m["files"][0]["id"]=123
        with self.assertRaisesRegex(ValueError,"file ID"):
            locate_publisher_file(m)

    def test_publisher_checksum_is_required(self):
        m=meta()
        m["files"][0]["computed_md5"]="bad"
        with self.assertRaisesRegex(ValueError,"MD5"):
            locate_publisher_file(m)

    def test_real_checksum_mismatch_is_rejected(self):
        raw=b"serial,stage\nA,1\n"
        p=pub(raw)
        with self.assertRaisesRegex(ValueError,"MD5"):
            inspect_original_csv(raw.replace(b"A,1",b"B,1"),p)

    def test_aggregate_serial_and_stage_counts_do_not_claim_physical_auth(self):
        raw=b"serial,stage,voltage_V\nA,one,3.1\nA,two,3.0\nB,one,2.9\n"
        d=inspect_original_csv(raw,pub(raw))
        self.assertEqual(d["record_rows"],3)
        self.assertEqual(d["distinct_serial_values"],2)
        self.assertEqual(d["distinct_stage_serial_pairs"],3)
        self.assertTrue(d["serial_alone_collides_across_stages"])
        self.assertEqual(d["valid_metadata_composite_identity_key"],["stage","serial"])
        self.assertFalse(d["cross_cell_confusion_rate_measured"])
        self.assertEqual(d["independently_authenticated_physical_cell_identities"],0)
        self.assertEqual(d["raw_cell_waveforms_downloaded"],0)

    def test_repeated_cell_rows_do_not_become_new_cell_ids(self):
        raw=b"serial,stage\nA,one\nA,one\nB,one\n"
        d=inspect_original_csv(raw,pub(raw))
        self.assertEqual(d["record_rows"],3)
        self.assertEqual(d["distinct_serial_values"],2)
        self.assertEqual(d["distinct_stage_serial_pairs"],2)
        self.assertEqual(d["composite_stage_serial_row_collisions"],1)
        self.assertIsNone(d["valid_metadata_composite_identity_key"])

    def test_no_serial_column_reports_unknown_not_fake_identity(self):
        raw=b"foo,other\nv,1\n"
        d=inspect_original_csv(raw,pub(raw))
        self.assertFalse(d["has_serial_column"])
        self.assertIsNone(d["distinct_serial_values"])

    def test_bad_row_extra_fields_rejected(self):
        raw=b"serial,stage\nA,one,extra\n"
        with self.assertRaisesRegex(ValueError,"inconsistent"):
            inspect_original_csv(raw,pub(raw))

    def test_csv_duplicate_column_names_rejected(self):
        raw=b"serial,serial\nA,B\n"
        with self.assertRaisesRegex(ValueError,"duplicate"):
            inspect_original_csv(raw,pub(raw))

    def test_invalid_csv_binary_is_rejected(self):
        raw=b"serial,x\nA,\x00\n"
        with self.assertRaisesRegex(ValueError,"binary"):
            inspect_original_csv(raw,pub(raw))


if __name__ == "__main__":
    unittest.main()
