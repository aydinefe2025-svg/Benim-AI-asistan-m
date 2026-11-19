"""No unzip-on-disk and no unsupported source/physical claims.

Fixtures are local *synthetic* ZIPs, NOT independent real cell observations.
"""
import hashlib
import io
import unittest
import zipfile
from research.battery_curve_audit.field_18471156_source import (
    inspect_zip_bytes,audit_original,MAX_DOWNLOAD_BYTES
)


def tiny_source(files=None, compression=zipfile.ZIP_DEFLATED):
    files = files or {"data/field.csv": b"time,cell1_V,cell2_V\n0,3.1,3.2\n1,3.0,3.1\n"}
    dest=io.BytesIO()
    with zipfile.ZipFile(dest,'w',compression=compression) as z:
        for name, content in files.items():
            z.writestr(name,content)
    return dest.getvalue()


class RealPublisherDataArchiveGate(unittest.TestCase):
    def test_source_md5_verification_blocks_modified_bytes_before_any_claim(self):
        raw=tiny_source()
        with self.assertRaisesRegex(ValueError,"MD5"):
            audit_original(raw)
        with self.assertRaisesRegex(ValueError,"MD5"):
            audit_original(raw+b"! ",expected_md5=hashlib.md5(raw).hexdigest())

    def test_valid_small_original_has_source_only_not_cell_truth(self):
        raw=tiny_source()
        result=audit_original(raw,expected_md5=hashlib.md5(raw).hexdigest())
        self.assertEqual(result["decision"],"SOURCE_INTEGRITY_ONLY_NOT_PHYSICAL_VALIDATION")
        self.assertEqual(result["publisher_md5_verified"],True)
        self.assertEqual(result["member_count"],1)
        self.assertEqual(result["format_counts"],{"csv":1})
        self.assertEqual(result["physical_cell_identity_confirmed"],False)
        self.assertEqual(result["license_for_commercial_reuse"],"NOT_VERIFIED")
        self.assertNotIn("original_rows",result)

    def test_archive_must_be_zip(self):
        with self.assertRaises(ValueError):
            inspect_zip_bytes(b"<html>403</html>")

    def test_path_traversal_refused(self):
        for path in ("../escape.csv","/etc/passwd","x/../../private.csv"):
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,"path"):
                inspect_zip_bytes(tiny_source({path:b"1,2\n"}))

    def test_case_duplicate_member_is_blocked(self):
        raw=tiny_source({"data/A.csv":b"x","data/a.csv":b"y"})
        with self.assertRaises(ValueError):
            inspect_zip_bytes(raw)

    def test_zip_member_crc_is_verified(self):
        raw=bytearray(tiny_source({"test.csv":b"1,2\n"},zipfile.ZIP_STORED))
        location=raw.find(b"1,2\n")
        self.assertGreater(location,0)
        raw[location]=ord("9")
        with self.assertRaises(ValueError):
            inspect_zip_bytes(bytes(raw))

    def test_oversized_file_input_is_rejected(self):
        with self.assertRaises(ValueError):
            inspect_zip_bytes(b"0"*(MAX_DOWNLOAD_BYTES+1))

    def test_source_header_inventory_is_not_physical_cell_groundtruth(self):
        raw=tiny_source({
            "batch/fileA.csv":b"Time,cell1_voltage,temperature_c\n0,3.1,25\n",
            "batch/fileB.csv":b"Time,cell2_voltage,temperature_c\n1,3.2,26\n",
        })
        result=inspect_zip_bytes(raw)
        self.assertEqual(result["header_column_count_histogram"],{"3":2})
        self.assertEqual(result["distinct_header_patterns"],2)
        self.assertIn("cell1_voltage",result["header_samples"][0])
        self.assertFalse(result["physical_cell_identity_confirmed"])

    def test_zip_does_not_make_up_cell_count_from_filename(self):
        result=inspect_zip_bytes(tiny_source({"cells_999.csv":b"a,b\n1,2\n"}))
        self.assertEqual(result["member_count"],1)
        self.assertFalse(result["physical_cell_identity_confirmed"])

if __name__=="__main__":
    unittest.main()
