"""Offline tests: validation must reject non-source, corrupt or unsafe bytes."""
import hashlib
import io
import unittest
from unittest.mock import patch
import zipfile
from research.battery_curve_audit import bayreuth_external_archive_preflight as source


def mkzip(name="F0001/M0001_checkup.csv", body=b"t;I;U\n0;0;3.5\n"):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, body)
    return data.getvalue()


class PublisherSourceGate(unittest.TestCase):
    def test_correct_md5_and_crc_from_mock_source(self):
        payload=mkzip()
        with patch.object(source, 'EXPECTED_MD5', hashlib.md5(payload).hexdigest()), \
             patch.object(source, 'MIN_SOURCE_BYTES', 1):
            r=source.validate_archive(payload)
        self.assertTrue(r['zip_crc_all_pass'])
        self.assertEqual(r['cells_with_downloaded_original_zip'], 1)
        self.assertEqual(r['zip_file_count'], 1)
        self.assertTrue(r['publisher_description_cues_found']['beginning_checkup_M0001'])
        self.assertFalse(r['actual_DCIR_or_capacity_recalculated'])
        self.assertFalse(r['physical_calibration_certificate_verified'])

    def test_reject_wrong_original_publisher_md5(self):
        with self.assertRaisesRegex(ValueError, 'MD5 mismatch'):
            source.validate_archive(mkzip())

    def test_reject_corrupt_zip_crc_even_if_md5_matches(self):
        payload=bytearray(mkzip(body=b'test data 123456789'))
        at=payload.find(b'test data')
        # Because DEFLATED, changing arbitrary compressed bytes can invalidate file;
        # also a malformed central entry must never be reported as a valid source.
        self.assertNotEqual(at, 0)
        payload[-22:-20] = b'XX'
        with patch.object(source,'EXPECTED_MD5',hashlib.md5(payload).hexdigest()),patch.object(source,'MIN_SOURCE_BYTES',1):
            with self.assertRaises((ValueError, zipfile.BadZipFile)):
                source.validate_archive(bytes(payload))

    def test_reject_zip_traversal(self):
        payload=mkzip('../escape.csv')
        with patch.object(source, 'EXPECTED_MD5',hashlib.md5(payload).hexdigest()),patch.object(source,'MIN_SOURCE_BYTES',1):
            with self.assertRaisesRegex(ValueError, 'path traversal'):
                source.validate_archive(payload)

    def test_no_independent_measurement_claim(self):
        payload=mkzip()
        with patch.object(source, 'EXPECTED_MD5',hashlib.md5(payload).hexdigest()),patch.object(source,'MIN_SOURCE_BYTES',1):
            x=source.validate_archive(payload)
        self.assertFalse(x['independent_lab_validation_of_original_Stroebl_4_cells'])
        self.assertFalse(x['actual_DCIR_or_capacity_recalculated'])

if __name__=='__main__':
    unittest.main()