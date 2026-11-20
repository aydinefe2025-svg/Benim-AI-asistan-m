"""Fail-closed author source protocol equivalence, not field acceptance."""
import unittest
from research.battery_curve_audit.figshare_protocol_equivalence import (
    compare_protocol_identifiers, inspect_sidecar_setup, crosscheck_publisher_row,
)

class SourceProtocolTests(unittest.TestCase):
    def test_strict_composite_tp_normalizes_publisher_number(self):
        out=compare_protocol_identifiers('TP_k01_05',{'type':'k','tp':'1','cell':'5'},'TP_k01')
        self.assertTrue(out['overview_filename_type_tp_cell_match'])
        self.assertTrue(out['sidecar_testpoint_equivalent'])
        self.assertFalse(out['physical_conditions_independently_verified'])

    def test_strict_full_sidecar_testpoint_matches_cell(self):
        out=compare_protocol_identifiers('TP_k01_05',{'type':'k','tp':'01','cell':'05'},'TP_k01_05')
        self.assertTrue(out['sidecar_testpoint_equivalent'])

    def test_sidecar_compact_testpoint_matches(self):
        out=compare_protocol_identifiers('TP_k01_05',{'type':'k','tp':'1','cell':'05'},'k01')
        self.assertTrue(out['sidecar_testpoint_equivalent'])

    def test_same_publisher_tp_but_wrong_calendar_type_rejected(self):
        out=compare_protocol_identifiers('TP_k01_05',{'type':'z','tp':'1','cell':'5'},'TP_k01')
        self.assertFalse(out['overview_filename_type_tp_cell_match'])
        self.assertEqual(out['decision'],'OVERVIEW_PROTOCOL_CONFLICT_REVIEW_REQUIRED')

    def test_wrong_cell_number_rejected(self):
        out=compare_protocol_identifiers('TP_k01_05',{'type':'k','tp':'1','cell':'6'},'TP_k01')
        self.assertFalse(out['overview_filename_type_tp_cell_match'])

    def test_sidecar_wrong_testpoint_not_silently_promoted(self):
        out=compare_protocol_identifiers('TP_k01_05',{'type':'k','tp':'1','cell':'5'},'TP_k02')
        self.assertFalse(out['sidecar_testpoint_equivalent'])
        self.assertEqual(out['decision'],'SIDECAR_TESTPOINT_CONFLICT_REVIEW_REQUIRED')

    def test_sidecar_wrong_cell_not_dropped(self):
        out=compare_protocol_identifiers('TP_k01_05',{'type':'k','tp':'1','cell':'5'},'TP_k01_06')
        self.assertFalse(out['sidecar_testpoint_equivalent'])

    def test_unrecognized_sidecar_is_unresolved_not_success(self):
        out=compare_protocol_identifiers('TP_k01_05',{'type':'k','tp':'1','cell':'5'},'calendar condition 01')
        self.assertIsNone(out['sidecar_testpoint_equivalent'])
        self.assertEqual(out['decision'],'SIDECAR_TESTPOINT_FORMAT_REVIEW_REQUIRED')

    def test_sidecar_missing_field_keeps_unverified(self):
        out=compare_protocol_identifiers('TP_k01_05',{'type':'k','tp':'1','cell':'5'},None)
        self.assertIsNone(out['sidecar_testpoint_equivalent'])

    def test_non_integral_tp_or_cell_rejected(self):
        for raw in ('1.5','nan','-1','1e0',''):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError,'integer|protocol'):
                compare_protocol_identifiers('TP_k01_05',{'type':'k','tp':raw,'cell':'5'},'TP_k01')

    def test_unknown_character_in_identifier_does_not_fuzzy_match(self):
        with self.assertRaisesRegex(ValueError,'source archive'):
            compare_protocol_identifiers('TP_k01_05/../../x',{'type':'k','tp':'1','cell':'5'},'TP_k01')

    def test_equipment_and_channel_are_separate_from_identity(self):
        out=inspect_sidecar_setup({'measurement_device_used':'Device-01','test_channel':'8',
                                   'measurement_start_date':'2022-03-06 10:21:00',
                                   'climate_chamber_used':'Chamber-1',
                                   'climate_chamber_temperature_setpoint':'23'})
        self.assertTrue(out['device_record_present'])
        self.assertTrue(out['channel_record_present'])
        self.assertTrue(out['start_time_record_parseable'])
        self.assertTrue(out['climate_chamber_record_present'])
        self.assertFalse(out['device_calibration_independently_verified'])
        self.assertNotIn('Device-01',str(out))

    def test_malformed_date_record_not_accepted(self):
        out=inspect_sidecar_setup({'measurement_device_used':'Dev','test_channel':'1',
                                   'measurement_start_date':'nonsense'})
        self.assertFalse(out['start_time_record_parseable'])

    def test_missing_equipment_channel_not_treated_as_lab_ready(self):
        out=inspect_sidecar_setup({'measurement_start_date':'2024-04-12'})
        self.assertFalse(out['device_record_present'])
        self.assertFalse(out['channel_record_present'])
        self.assertFalse(out['all_required_source_setup_labels_present'])

    def test_crosscheck_publisher_row_rejects_inconsistent_metadata(self):
        out=crosscheck_publisher_row('TP_k01_05',{'type':'z','tp':'1','cell':'5'},
                 {'testpoint':'TP_k01','measurement_device_used':'D','test_channel':'A',
                  'measurement_start_date':'2024-01-01'})
        self.assertFalse(out['publisher_record_protocol_consistent'])
        self.assertEqual(out['field_acceptance'],'NOT_ESTABLISHED')

if __name__=='__main__': unittest.main()