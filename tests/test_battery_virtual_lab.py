"""Synthetic matrix must be reproducible and the before/after limitations explicit."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'research'/'battery_curve_audit'))
import battery_virtual_lab as lab

class VirtualBatteryLabTests(unittest.TestCase):
    def test_all_13_synthetic_families_without_regression(self):
        report=lab.run_all(trials=2,seed=20261119)
        self.assertEqual(report['total_simulated_batches'],26)
        self.assertEqual(report['total_generated_curves'],104)
        self.assertEqual(len(report['categories']),13)
        self.assertEqual(report['baseline_deviations'],0)
        self.assertEqual(report['controlled_clone_screen_only_misses'],2)
        self.assertEqual(report['controlled_clone_batches'],12)
        self.assertEqual(report['input_error_batches'],4)
        self.assertNotIn('all_trials',report)

    def test_timestamp_origin_clones_are_grouped_for_holdout(self):
        result=lab.run_case('time_origin_shift_clone',0,seed=20261119)
        self.assertEqual(result['decision'],'REVIEW_REQUIRED')
        self.assertTrue(result['A_B_same_connected_group'])
        self.assertGreater(result['near_candidates'],0)

    def test_alternative_bias_correction_overflags_independent_templates(self):
        report=lab.run_all(trials=2,seed=20261119)
        alternatives=report['experimental_second_stage']
        self.assertTrue(alternatives['NOT_DEPLOYED_OR_CERTIFIED'])
        self.assertEqual(alternatives['bias_removed_controlled_clone_candidates'],12)
        self.assertEqual(alternatives['bias_removed_independent_template_candidates'],4)
        self.assertEqual(report['independent_templates_flagged_for_review'],2)

    def test_falsely_missed_overthreshold_bias_is_reported_not_silenced(self):
        r=lab.run_case('noisy_clone_3mv',1,seed=20261119)
        self.assertEqual(r['decision'],'SCREEN_ONLY_NO_CROSS_CELL_CANDIDATES')
        self.assertFalse(r['A_B_same_connected_group'])
        self.assertTrue(r['counterfactual_voltage_bias_removed_AB_candidate'])

    def test_bad_trial_count_rejected(self):
        for n in [-1,0,1001]:
            with self.subTest(n=n),self.assertRaises(ValueError):
                lab.run_all(trials=n,seed=1)

if __name__=='__main__':unittest.main()
