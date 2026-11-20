"""Adversarial synthetic tests, not measured physical-cell acceptance."""
import io
from hashlib import md5
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from research.battery_curve_audit.zenodo19380245_three_cell_source import (
    RECORD_ID, DOI, NAME, PUBLISHER_MD5, inspect_archive, validate_publisher_metadata,
)


def metadata():
    return {"id": RECORD_ID, "metadata": {"doi": DOI,
            "rights": [{"id": "cc-by-4.0"}]},
            "files": [{"key": NAME, "size": 1024, "checksum": "md5:" + PUBLISHER_MD5}]}


def make_zip(files):
    dst = io.BytesIO()
    with ZipFile(dst, "w", compression=ZIP_DEFLATED) as z:
        for name, body in files.items():
            z.writestr(name, body)
    return dst.getvalue()


def audit(raw):
    return inspect_archive(raw, {"original_size": len(raw),
                                 "publisher_md5": md5(raw).hexdigest()})


class RealSourceGuardTests(unittest.TestCase):
    def test_metadata_strict_source(self):
        found = validate_publisher_metadata(metadata())
        self.assertEqual(found["license"], "CC_BY_4_0_ZENODO_RECORD")

    def test_reject_wrong_record_and_doi(self):
        m = metadata(); m["id"] += 1
        with self.assertRaisesRegex(ValueError, "record ID"):
            validate_publisher_metadata(m)
        m = metadata(); m["metadata"]["doi"] = "10.5281/zenodo.999999"
        with self.assertRaisesRegex(ValueError, "DOI"):
            validate_publisher_metadata(m)

    def test_reject_unknown_license_and_wrong_digest(self):
        m = metadata(); m["metadata"]["rights"] = [{"id": "cc-by-nc-4.0"}]
        with self.assertRaisesRegex(ValueError, "license"):
            validate_publisher_metadata(m)
        m = metadata(); m["files"][0]["checksum"] = "md5:" + "0" * 32
        with self.assertRaisesRegex(ValueError, "checksum"):
            validate_publisher_metadata(m)

    def test_reject_duplicate_or_wrong_source(self):
        m = metadata(); m["files"].append(m["files"][0].copy())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_publisher_metadata(m)
        m = metadata(); m["files"][0]["key"] = "other.zip"
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_publisher_metadata(m)

    def test_reject_source_byte_tamper(self):
        z = make_zip({"Cell_1/c.csv": "time(s),voltage(V),current(A)\n0,3.3,1\n"})
        with self.assertRaisesRegex(ValueError, "MD5 mismatch"):
            inspect_archive(z, {"original_size": len(z),
                                "publisher_md5": "0" * 32})

    def test_reject_html_and_zip_path_traversal(self):
        with self.assertRaisesRegex(ValueError, "not ZIP"):
            audit(b"<!doctype html>")
        z = make_zip({"../escape.csv": "time,voltage,current\n0,3.4,1\n"})
        with self.assertRaisesRegex(ValueError, "unsafe"):
            audit(z)

    def test_reject_duplicate_member_names(self):
        b = io.BytesIO()
        with ZipFile(b, "w", compression=ZIP_DEFLATED) as z:
            z.writestr("Cell_1/Test.csv", "time,voltage,current\n0,3,1\n")
            z.writestr("cell_1/test.CSV", "time,voltage,current\n0,3,1\n")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit(b.getvalue())

    def test_three_distinct_folders_not_physical_cell_attestation(self):
        z = make_zip({
            "Cell_1/a.csv": "Time(s),Voltage(V),Current(A)\n0,3.3,1\n1,3.4,1\n",
            "Cell_2/a.csv": "Time(s),Voltage(V),Current(A)\n0,3.2,2\n1,3.4,2\n",
            "Cell_3/a.csv": "Time(s),Voltage(V),Current(A)\n0,3.1,3\n1,3.4,3\n"})
        receipt = audit(z)
        self.assertEqual(receipt["zip_file_count"], 3)
        self.assertEqual(receipt["csv_examples_crc_verified"], 3)
        self.assertEqual(receipt["csv_example_column_checks"], {"t1v1i1": 3})
        self.assertFalse(receipt["time_axis_per_cell_verified"])
        self.assertFalse(receipt["empirical_false_match_rate_calculated"])
        self.assertFalse(receipt["customer_release_allowed"])

    def test_time_missing_never_claims_physical_screening(self):
        z = make_zip({"Cell_1/no_time.csv": "Voltage,Current\n3.2,1\n"})
        r = audit(z)
        self.assertEqual(r["csv_example_column_checks"], {"t0v1i1": 1})
        self.assertFalse(r["empirical_false_match_rate_calculated"])


    def test_instrument_preamble_and_semicolon_header(self):
        content = "Metadata for equipment\nTime (s);Voltage (V);Current (A)\n0;3.3;1\n"
        r = audit(make_zip({"Cell_1/pre.csv": content}))
        self.assertEqual(r["csv_example_column_checks"], {"t1v1i1": 1})
        self.assertFalse(r["time_axis_per_cell_verified"])

    def test_numeric_first_line_is_never_exposed_as_header(self):
        r = audit(make_zip({"Cell_1/values.csv": "0,3.3,1\n1,3.4,1\n"}))
        self.assertEqual(r["csv_example_column_checks"], {"unrecognized_or_preamble_only": 1})
        self.assertEqual(r["csv_examples"][0]["header_names"], [])
        self.assertFalse(r["empirical_false_match_rate_calculated"])



    def test_cross_rate_exact_copy_confirmed_not_a_false_match_rate(self):
        source = "time(s),voltage(v),current(a)\n0,3.1,1\n1,3.2,1\n"
        r = audit(make_zip({
            "1C/a.csv": source, "2C/b.csv": source,
            "2.75C/c.csv": "time(s),voltage(v),current(a)\n0,3.5,2\n"}))
        self.assertTrue(r["cross_rate_duplicate_audit_complete"])
        self.assertEqual(r["cross_rate_exact_sha256_duplicate_clusters"], 1)
        self.assertEqual(r["cross_rate_exact_duplicate_member_count"], 2)
        self.assertFalse(r["empirical_false_match_rate_calculated"])

    def test_distinct_cross_rate_files_do_not_conflate_crc_candidates(self):
        r = audit(make_zip({
            "1C/a.csv": "time,voltage,current\n0,3.11,1\n",
            "2C/b.csv": "time,voltage,current\n0,3.42,1\n"}))
        self.assertEqual(r["cross_rate_exact_sha256_duplicate_clusters"], 0)
        self.assertTrue(r["cross_rate_duplicate_audit_complete"])



if __name__ == "__main__":
    unittest.main()
