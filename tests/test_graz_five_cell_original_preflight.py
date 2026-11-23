"""Fail-closed tests: fake ZIP is not passed off as real Graz evidence."""
import io
import zipfile
import unittest
from research.battery_curve_audit import graz_five_cell_original_preflight as m


def fixture_record():
    return {"id":int(m.RECORD_ID), "doi":m.DOI, "files":[
        {"key":m.ARCHIVE_NAME, "checksum":"md5:"+m.PUBLISHER_MD5,
         "size":10_800_000, "links":{"content":m.API+"/files/mock/content"}}],
        "metadata":{"rights":[{"id":"cc-by-4.0"}]}}


def fixture_zip(files=None):
    if files is None:
        files={"Cell01/01_log.csv":"time_s,current_A\n0,1\n1,1\n",
               "Cell01/01_SP.csv":"time_s,thickness_mm\n0,10\n1,10.1\n"}
    b=io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return b.getvalue()


class TestGrazOriginalPreflight(unittest.TestCase):
    def test_exact_five_cell_record_not_the_four_cell_record(self):
        spec=m.validate_manifest(fixture_record())
        self.assertEqual(spec["md5"],m.PUBLISHER_MD5)
        self.assertEqual(spec["license_ids_from_publisher_record"],["cc-by-4.0"])
        self.assertEqual(m.PUBLISHER_CELLS,{"01":0,"02":1.5,"03":3,"04":5,"05":15})
        x=fixture_record()
        x["id"]=18315429
        with self.assertRaisesRegex(ValueError,"wrong record identity"):
            m.validate_manifest(x)

    def test_tampered_publisher_pin_and_redirect_rejected(self):
        x=fixture_record()
        x["files"][0]["checksum"]="md5:" + "0"*32
        with self.assertRaisesRegex(ValueError,"checksum"):
            m.validate_manifest(x)
        x=fixture_record()
        x["files"][0]["links"]["content"]="https://example.com/malware"
        with self.assertRaisesRegex(ValueError,"fixed Zenodo"):
            m.validate_manifest(x)

    def test_valid_structural_fixture_is_not_a_real_measurement(self):
        r=m.audit_archive(fixture_zip())
        self.assertTrue(r["zip_crc_all_members_pass"])
        self.assertEqual(r["file_count"],2)
        self.assertEqual(r["file_extension_counts"],{".csv":2})
        self.assertTrue(any(x["header_preview"][0].startswith("time_s") for x in r["file_members"]))

    def test_zip_traversal_or_duplicate_names_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"unsafe"):
            m.audit_archive(fixture_zip({"../escape.csv":"fake"}))
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w") as z:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                z.writestr("same.csv","a")
                z.writestr("same.csv","b")
        with self.assertRaisesRegex(ValueError,"duplicate"):
            m.audit_archive(b.getvalue())

    def test_invalid_bytes_not_accepted(self):
        with self.assertRaises(ValueError):
            m.audit_archive(b"not a ZIP")
        with self.assertRaises(ValueError):
            m.audit_archive(b"")


if __name__ == "__main__":
    unittest.main()
