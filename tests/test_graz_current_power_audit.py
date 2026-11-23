"""Tests explicitly distinguish numerical consistency from real SI unit certificates."""
import io
import json
import math
import unittest
import zipfile
from research.battery_curve_audit import graz_current_power_audit as p


class PowerAudit(unittest.TestCase):
    def test_exact_numeric_scale_1_not_calibration(self):
        d=p.numeric_scale_audit([(3.5, i, 3.5*i) for i in range(1, 100)])
        self.assertEqual(d['median_numeric_power_to_voltage_current_ratio'], 1.)
        self.assertEqual(d['fraction_numerically_near_ratio_1_within_5pct'], 1.)
        self.assertFalse(d['independent_units_calibrated'])

    def test_power_milliscale_is_distinguishable_not_certified(self):
        d=p.numeric_scale_audit([(4., i, 4*i*.001) for i in range(1, 100)])
        self.assertEqual(d['candidate_numeric_ratio_reference'], 'numeric_P_over_VI_0.001')
        self.assertFalse(d['independent_units_calibrated'])

    def test_sign_inversion_is_not_automatically_clamped(self):
        d=p.numeric_scale_audit([(3.7, 10, -37.) for _ in range(200)])
        self.assertEqual(d['candidate_numeric_ratio_reference'], 'numeric_P_over_VI_minus_1')
        self.assertFalse(d['independent_units_calibrated'])

    def test_eligible_denominator_safety(self):
        d=p.numeric_scale_audit([(3.7, 0.0, 0.0)]*20)
        self.assertIsNone(d['candidate_numeric_ratio_reference'])
        self.assertEqual(d['eligible_records'], 0)

    def test_nonfinite_rejected(self):
        for val in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):p.numeric_scale_audit([(4., 1., val)])
        with self.assertRaises(ValueError):p.finite('nan')

    def _source_zip(self, rows, header='Time,Device,Voltage,Current,Power'):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as z:
            z.writestr('cell 02/test_log.txt', header+'\n'+''.join(rows))
        return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))

    def _rows(self, number=150):
        return [f'2024-10-28_10-11-12-{i:06d},COM3,3.7,2,7.4\n' for i in range(number)]

    def test_parser_150_real_format_rows(self):
        with self._source_zip(self._rows()) as z:
            d=p.audit_electrical_member(z,z.infolist()[0],cell='02')
        self.assertEqual(d['genuine_original_row_count'],150)
        self.assertEqual(d['source_device_labels'],{'COM3':150})
        self.assertEqual(d['numeric_consistency_sample_only']['fraction_numerically_near_ratio_1_within_5pct'],1.)
        self.assertFalse(d['calibrated_current_unit_A'])

    def test_header_mutation_rejected(self):
        with self._source_zip(self._rows(),header='Time,Device,Voltage,Ampere,Power') as z:
            with self.assertRaisesRegex(ValueError,'header'):p.audit_electrical_member(z,z.infolist()[0],cell='02')

    def test_row_missing_field_rejected(self):
        with self._source_zip(['2024-10-28_10-11-12-123456,COM3,3.7,2\n']*150) as z:
            with self.assertRaisesRegex(ValueError,'row shape'):p.audit_electrical_member(z,z.infolist()[0],cell='02')

    def test_unknown_device_rejected(self):
        with self._source_zip(['2024-10-28_10-11-12-123456,VIRTUAL,3.7,2,7.4\n']*150) as z:
            with self.assertRaisesRegex(ValueError,'device'):p.audit_electrical_member(z,z.infolist()[0],cell='02')

    def test_overlarge_row_numeric_rejected(self):
        with self._source_zip(['2024-10-28_10-11-12-123456,COM3,3.7,20000,7.4\n']*150) as z:
            with self.assertRaisesRegex(ValueError,'range'):p.audit_electrical_member(z,z.infolist()[0],cell='02')

    def test_empty_and_too_short_source_rejected(self):
        with self._source_zip(self._rows(number=2)) as z:
            with self.assertRaisesRegex(ValueError,'too short'):p.audit_electrical_member(z,z.infolist()[0],cell='02')

    def test_randomized_reservoir_is_deterministic(self):
        rows=self._rows(number=5100)
        with self._source_zip(rows) as z:
            a=p.audit_electrical_member(z,z.infolist()[0],cell='02')
            b=p.audit_electrical_member(z,z.infolist()[0],cell='02')
        self.assertEqual(a,b)
        self.assertEqual(a['bounded_deterministic_reservoir_size'],3000)

    def test_wrong_archive_blocked_before_science(self):
        with self.assertRaises(Exception):p.inspect_original(b'fake',len(b'fake'))

    def test_no_empirical_units_claim_on_noisy_ratio(self):
        d=p.numeric_scale_audit([(4.,2.,7.5+i/100.) for i in range(50)])
        self.assertIsNone(d['candidate_numeric_ratio_reference'])
        self.assertFalse(d['independent_units_calibrated'])


if __name__ == '__main__':unittest.main()