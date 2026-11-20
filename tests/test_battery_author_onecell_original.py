"""All test records synthetic; original author CSV checked only by GitHub CI."""
import hashlib
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'/'battery_publisher_sample'))
import author_onecell_original as one


def fixture(n=130,*,header='run_time,c_vol,c_cur,step_type'):
    return (header+'\n'+'\n'.join(f'00:00:{i//5:02d}.{i%5}, {4.2-i*.004:.4f},-1.4,{41 if i<75 else 42}' for i in range(n))+'\n').encode('ascii')


def inspect(raw):
    return one.inspect_csv(raw,expected_bytes=len(raw),expected_blob=one.git_blob_sha1(raw))


class OriginalAuthorRealSamplingTests(unittest.TestCase):
    def test_positive_timestamp_voltage_current_and_step_group(self):
        data=fixture()
        result=inspect(data)
        self.assertEqual(result['full_time_voltage_sample_rows'],130)
        self.assertEqual(result['source_status'],'AUTHORS_GITHUB_ORIGINAL_GIT_BLOB_VERIFIED')
        self.assertEqual(result['time_decreasing_steps'],0)
        self.assertEqual(result['time_axis_name'],'run_time')
        self.assertGreater(result['voltage_span_V'],.5)
        self.assertFalse(result['physical_cell_independence_verified'])
        self.assertFalse(result['source_publisher_figshare_byte_identity_verified'])
        self.assertFalse(result['field_false_match_rate_measured'])
    def test_tampered_csv_without_new_pin_refused(self):
        raw=fixture()
        with self.assertRaisesRegex(ValueError,'blob'):
            one.inspect_csv(raw.replace(b'-1.4',b'-2.4'),expected_bytes=len(raw),expected_blob=one.git_blob_sha1(raw))
    def test_malformed_header_missing_true_time(self):
        raw=fixture(header='index,c_vol,c_cur,step_type')
        with self.assertRaisesRegex(ValueError,'timestamp'):
            inspect(raw)
    def test_missing_current_is_not_disguised_as_voltage(self):
        raw=fixture(header='run_time,c_vol,noise,step_type')
        with self.assertRaisesRegex(ValueError,'current'):
            inspect(raw)
    def test_duplicate_header_rejected(self):
        raw=fixture(header='run_time,c_vol,c_vol,step_type')
        with self.assertRaisesRegex(ValueError,'columns'):
            inspect(raw)
    def test_nonfinite_numeric_rejected(self):
        raw=fixture().replace(b'4.2000',b'nan   ')
        with self.assertRaisesRegex(ValueError,'invalid numeric'):
            inspect(raw)
    def test_negative_timestamp_rejected(self):
        raw=fixture().replace(b'00:00:00.0',b'-10')
        with self.assertRaisesRegex(ValueError,'time'):
            inspect(raw)
    def test_timestamp_regression_is_reported_not_misdeclared_monotone(self):
        raw=fixture().replace(b'00:00:10.1',b'00:00:01.1')
        x=inspect(raw)
        self.assertGreater(x['time_decreasing_steps'],0)
        self.assertLess(x['longest_consecutive_same_step_monotone_segment'],130)
    def test_irregular_sample_has_no_imputed_pairs(self):
        raw=fixture(99)
        with self.assertRaisesRegex(ValueError,'too short'):
            inspect(raw)
    def test_refuse_output_overwrite_before_remote_fetch(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'out.json'
            p.write_text('PRESERVE',encoding='utf-8')
            with patch.object(one,'fetch_original_author_csv',side_effect=AssertionError('called!')):
                self.assertEqual(one.main([str(p)]),2)
            self.assertEqual(p.read_text(),'PRESERVE')
    def test_git_blob_pin_is_not_plain_content_sha(self):
        raw=fixture()
        self.assertNotEqual(one.git_blob_sha1(raw),hashlib.sha1(raw).hexdigest())

if __name__=='__main__':unittest.main()
