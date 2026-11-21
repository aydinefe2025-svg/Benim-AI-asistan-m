"""Offline, deterministic regression tests for source-identity acceptance denial."""
import unittest
from research.battery_curve_audit.figshare_cross_stage_real_identity import (
    check_distinct_publisher_labels, score_fixed_condition, EXPECTED_PUBLIC_CELLS,
)

NAMES=sorted(('TP_k01_04','TP_k01_05','TP_k01_06','TP_k04_04','TP_k04_05','TP_k04_06'))

def wave(shift):
    return tuple((float(i),3.0+shift+0.001*i) for i in range(60))

class PublishedIdentityStressTest(unittest.TestCase):
    def test_six_distinct_labels(self):
        check_distinct_publisher_labels([('A',str(i)) for i in range(6)])

    def test_duplicate_publisher_cell_identity_blocks(self):
        with self.assertRaisesRegex(ValueError,'colliding'):
            check_distinct_publisher_labels([('A','c0'),(' a ','C0'),('A','c2'),('A','c3'),('A','c4'),('A','c5')])

    def test_blank_lab_serial_blocks(self):
        with self.assertRaisesRegex(ValueError,'missing'):
            check_distinct_publisher_labels([('A',str(i)) for i in range(5)]+[('','6')])

    def test_wrong_cohort_blocks(self):
        with self.assertRaisesRegex(ValueError,'exact six-cell'):
            score_fixed_condition({NAMES[0]:wave(0)}, {NAMES[0]:wave(0)})

    def test_same_source_replay_wins_when_unambiguously_distinct(self):
        data={n:wave(0.1*i) for i,n in enumerate(NAMES)}
        scores=score_fixed_condition(data,data)
        self.assertEqual(len(scores),EXPECTED_PUBLIC_CELLS)
        self.assertEqual(sum(s['matching_publisher_cell_AT_rank']==1 for s in scores),6)
        self.assertEqual(sum(s['same_source_near_duplicate_rule_matches'] for s in scores),6)
        self.assertEqual(sum(s['cross_source_near_duplicate_alerts'] for s in scores),0)

    def test_remeasured_same_cell_can_be_different_but_its_identity_is_label_grounded(self):
        data={n:wave(0.1*i) for i,n in enumerate(NAMES)}
        new={n:wave(0.1*i+0.020) for i,n in enumerate(NAMES)}
        scores=score_fixed_condition(data,new)
        self.assertEqual(sum(s['same_source_near_duplicate_rule_matches'] for s in scores),0)
        self.assertEqual(sum(s['cross_source_near_duplicate_alerts'] for s in scores),0)
        self.assertEqual(sum(s['matching_publisher_cell_AT_rank']==1 for s in scores),6)

    def test_shift_can_break_nearest_neighbor_identity_even_when_label_matches(self):
        et={n:wave(0.1*i) for i,n in enumerate(NAMES)}
        at={n:wave(0.1*(5-i)) for i,n in enumerate(NAMES)}
        scores=score_fixed_condition(et,at)
        self.assertEqual(sum(s['matching_publisher_cell_AT_rank']==1 for s in scores),0)

    def test_ranking_ties_are_deterministic_and_not_truth(self):
        et={n:wave(0) for n in NAMES};at={n:wave(0.1) for n in NAMES}
        scores=score_fixed_condition(et,at)
        self.assertEqual(sum(s['matching_publisher_cell_AT_rank']==1 for s in scores),1)

if __name__=='__main__':unittest.main()