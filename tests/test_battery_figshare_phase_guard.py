"""Behavioral source-window phase/current guard tests; fixtures are synthetic."""
import unittest
from decimal import Decimal as D
from research.battery_curve_audit.figshare_phase_guard import compare_phase_controlled


def window(n=1500, *, jitter='0', step='ET_T23', current='-0.1', voltage='4.1', origin='0'):
    return {'points': [(D(origin)+D(i)+D(jitter), D(voltage), D(current), step) for i in range(n)]}


class PhaseGuardTests(unittest.TestCase):
    def test_identical_aligned_source_is_candidate_not_certification(self):
        a = compare_phase_controlled(window(), window())
        self.assertEqual(a['matched_unique_elapsed_time_points'], 1500)
        self.assertEqual(a['same_step_and_current_points'], 1500)
        self.assertEqual(a['exact_voltage_pairs'], 1500)
        self.assertEqual(a['near_2mV_voltage_pairs'], 1500)
        self.assertEqual(a['decision'], 'BOUNDED_REGIME_OVERLAP_RESEARCH_ONLY')
        self.assertFalse(a['physical_phase_alignment_authenticated'])
        self.assertFalse(a['independent_cell_identity_authenticated'])
        self.assertFalse(a['field_FPR_FNR_established'])

    def test_bounded_clock_jitter_does_not_force_false_uncomparable(self):
        a = compare_phase_controlled(window(), window(jitter='0.25'))
        self.assertEqual(a['matched_unique_elapsed_time_points'], 1500)
        self.assertEqual(a['same_step_and_current_points'], 1500)
        self.assertEqual(a['max_pair_time_delta_seconds'], '0.25')

    def test_difference_above_tolerance_never_interpolated(self):
        a = compare_phase_controlled(window(), window(jitter='0.6'))
        self.assertEqual(a['matched_unique_elapsed_time_points'], 0)
        self.assertEqual(a['decision'], 'NO_BOUNDED_TIME_OVERLAP')
        self.assertIsNone(a['exact_voltage_pairs'])

    def test_step_type_mismatch_is_excluded_before_voltage_comparison(self):
        a = compare_phase_controlled(window(), window(step='OTHER'))
        self.assertEqual(a['matched_unique_elapsed_time_points'], 1500)
        self.assertEqual(a['same_step_and_current_points'], 0)
        self.assertEqual(a['decision'], 'INSUFFICIENT_SAME_REGIME_PAIRS')
        self.assertIsNone(a['near_2mV_voltage_pairs'])

    def test_current_mismatch_is_excluded_before_voltage_comparison(self):
        a = compare_phase_controlled(window(), window(current='1.5'))
        self.assertEqual(a['same_step_and_current_points'], 0)
        self.assertEqual(a['same_step_points'], 1500)
        self.assertEqual(a['decision'], 'INSUFFICIENT_SAME_REGIME_PAIRS')
        self.assertIsNone(a['exact_voltage_pairs'])

    def test_bounded_current_difference_and_2mv_voltage_observation(self):
        a = compare_phase_controlled(window(), window(current='-0.11', voltage='4.101'))
        self.assertEqual(a['same_step_and_current_points'], 1500)
        self.assertEqual(a['near_2mV_voltage_pairs'], 1500)
        self.assertEqual(a['exact_voltage_pairs'], 0)
        self.assertEqual(a['max_voltage_delta_volts'], '0.001')

    def test_duplicate_source_timestamps_are_excluded_not_double_counted(self):
        w=window()
        w['points'].insert(12, w['points'][12])
        a=compare_phase_controlled(w, window())
        self.assertEqual(a['left_ambiguous_time_rows_excluded'], 2)
        self.assertEqual(a['matched_unique_elapsed_time_points'], 1499)
        self.assertEqual(a['same_step_and_current_points'], 1499)

    def test_unequal_lengths_match_only_common_portion_without_extrapolation(self):
        a=compare_phase_controlled(window(1700),window(1500))
        self.assertEqual(a['matched_unique_elapsed_time_points'], 1500)
        self.assertEqual(a['same_step_and_current_points'], 1500)
        self.assertEqual(a['left_unmatched_unique_elapsed_time_points'], 200)

    def test_short_overlap_does_not_infer_clean_signal(self):
        a=compare_phase_controlled(window(400), window(400))
        self.assertEqual(a['same_step_and_current_points'], 400)
        self.assertEqual(a['decision'], 'INSUFFICIENT_SAME_REGIME_PAIRS')
        self.assertIsNone(a['exact_voltage_pairs'])

    def test_nonmonotonic_points_fail_closed(self):
        w=window()
        w['points'][5]=(D(-1), D('4.1'), D('-0.1'), 'ET_T23')
        with self.assertRaisesRegex(ValueError, 'not monotonic'):
            compare_phase_controlled(w,window())

    def test_repeated_timestamp_with_conflicting_step_is_not_counted(self):
        a=window()
        t,v,c,step = a['points'][12]
        a['points'].insert(12,(t,D('0'),D('8'), 'OTHER'))
        x=compare_phase_controlled(a, window())
        self.assertEqual(x['same_step_and_current_points'],1499)
        self.assertEqual(x['near_2mV_voltage_pairs'],1499)


if __name__=='__main__': unittest.main()