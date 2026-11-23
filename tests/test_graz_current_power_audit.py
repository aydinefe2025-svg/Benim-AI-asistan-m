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

    def test_full_scan_device_channels_are_not_mixed(self):
        rows = [f'2024-10-28_10-11-12-{i:06d},COM3,3.7,2,7.4\n' for i in range(100)]
        rows += [f'2024-10-28_10-11-13-{i:06d},COM4,3.7,2,0.0074\n' for i in range(100)]
        with self._source_zip(rows) as z:
            d = p.audit_electrical_member(z, z.infolist()[0], cell='02')
        a = d['per_device_full_original_nonzero_vi_consistency']
        self.assertEqual(a['COM3']['full_scan_fraction_numerically_near_ratio_1_5pct'], 1.)
        self.assertEqual(a['COM4']['full_scan_fraction_numerically_near_ratio_1_5pct'], 0.)
        self.assertFalse(a['COM3']['independent_unit_calibration_verified'])
        self.assertEqual(d['nonzero_numeric_vi_rows_total'], 200)

    def test_relative_outlier_due_to_roundoff_is_reported_not_erased(self):
        rows = [f'2024-10-28_10-11-12-{i:06d},COM4,3.7,0.01,0.04\n' for i in range(150)]
        with self._source_zip(rows) as z:
            d = p.audit_electrical_member(z, z.infolist()[0], cell='02')
        w=d['per_device_full_original_nonzero_vi_consistency']['COM4']
        self.assertEqual(w['numerically_near_ratio_1_5pct_rows'],0)
        self.assertEqual(w['deviating_relative_gt_5pct_binned_by_abs_vi']['0.01_to_0.1'],150)
        self.assertEqual(w['deviating_relative_gt_5pct_with_abs_P_minus_VI_le_0.01'],150)
        self.assertEqual(w['deviating_relative_gt_5pct_with_abs_P_minus_VI_gt_0.1'],0)

    def test_large_relative_and_absolute_disagreement_flagged(self):
        rows = [f'2024-10-28_10-11-12-{i:06d},COM4,3.7,2,5.0\n' for i in range(150)]
        with self._source_zip(rows) as z:
            d = p.audit_electrical_member(z, z.infolist()[0], cell='02')
        w=d['per_device_full_original_nonzero_vi_consistency']['COM4']
        self.assertEqual(w['deviating_relative_gt_5pct_binned_by_abs_vi']['1_and_above'],150)
        self.assertEqual(w['deviating_relative_gt_5pct_with_abs_P_minus_VI_gt_0.1'],150)

    def test_deviation_rows_have_exact_replayable_provenance_not_raw_readings(self):
        rows = [f'2024-10-28_10-11-12-{i:06d},COM4,3.7,2,5.0\n' for i in range(150)]
        with self._source_zip(rows) as z:
            d=p.audit_electrical_member(z,z.infolist()[0],cell='02')
        q=d['numerical_discrepancy_review_queue_rows']
        self.assertEqual(len(q),150)
        self.assertEqual(q[0]['original_source_line_number'],2)
        self.assertEqual(q[-1]['original_source_line_number'],151)
        self.assertEqual(q[0]['original_timestamp_token'],'2024-10-28_10-11-12-000000')
        self.assertEqual(len(q[0]['original_raw_row_sha256']),64)
        self.assertNotIn('current',q[0])
        self.assertNotIn('power',q[0])
        self.assertTrue(d['quarantine_is_for_joint_V_I_P_numeric_use_only'])

    def test_consistent_numeric_rows_are_not_quarantined(self):
        with self._source_zip(self._rows()) as z:
            d=p.audit_electrical_member(z,z.infolist()[0],cell='02')
        self.assertEqual(d['numeric_discrepancy_review_queue_count'],0)

    def test_no_negative_current_is_recorded_without_phase_inference(self):
        rows = [f'2024-10-28_10-11-12-{i:06d},COM3,3.7,-2,-7.4\n' for i in range(150)]
        with self._source_zip(rows) as z:
            d = p.audit_electrical_member(z, z.infolist()[0], cell='02')
        self.assertEqual(d['negative_current_rows'], 150)
        self.assertFalse(d['independently_verified_charge_discharge_steps'])

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