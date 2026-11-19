"""Two-reviewer identity alias regressions. Synthetic metadata, not human ID proof."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'battery_curve_audit'))
import field_pilot_evidence as pilot


def ledger():
    return {
        'schema': pilot.SCHEMA,
        'site_authorization': {'permitted': True, 'reference': 'SYNTHETIC'},
        'audit_receipt_sha256': 'a' * 64,
        'cells': [
            {'cell': c, 'device': 'D-' + c, 'batch': 'B-' + c, 'campaign': 'C-' + c}
            for c in 'ABCD'
        ],
        'assignments': [
            {'cell': c, 'partition': partition}
            for c, partition in zip('ABCD', ('train', 'validation', 'test', 'train'))
        ],
        'screened_pair_count': 6, 'screened_flagged_count': 0,
        'reviews': [
            {'a': 'A', 'b': 'B', 'flagged': False,
             'reviewer_a': {'id': 'TECH-1', 'verdict': 'independent'},
             'reviewer_b': {'id': 'TECH-2', 'verdict': 'independent'}}
        ],
    }


class ReviewerIdentityGuardTests(unittest.TestCase):
    def test_case_and_outer_padding_alias_is_not_two_independent_reviewers(self):
        x = ledger()
        x['reviews'][0]['reviewer_b']['id'] = '  tech-1  '
        with self.assertRaisesRegex(ValueError, 'reviewer.*differ'):
            pilot.assess(x)

    def test_nfkc_fullwidth_alias_is_not_two_independent_reviewers(self):
        x = ledger()
        x['reviews'][0]['reviewer_b']['id'] = 'ＴＥＣＨ－１'
        with self.assertRaisesRegex(ValueError, 'reviewer.*differ'):
            pilot.assess(x)

    def test_invisible_control_char_reviewer_id_is_not_accepted(self):
        x = ledger()
        x['reviews'][0]['reviewer_b']['id'] = 'TECH\u200b-2'
        with self.assertRaisesRegex(ValueError, 'reviewer|control|format'):
            pilot.assess(x)

    def test_unicode_newline_reviewer_id_is_not_accepted(self):
        x = ledger()
        x['reviews'][0]['reviewer_a']['id'] = 'TECH-1\n'
        with self.assertRaisesRegex(ValueError, 'reviewer|control|format'):
            pilot.assess(x)

    def test_alias_with_unknown_verdict_still_refused(self):
        x = ledger()
        x['reviews'][0]['reviewer_a']['verdict'] = 'unknown'
        x['reviews'][0]['reviewer_b']['id'] = 'tech-1'
        with self.assertRaisesRegex(ValueError, 'reviewer.*differ'):
            pilot.assess(x)

    def test_distinct_reviewer_ids_remain_valid_local_annotations(self):
        x = ledger()
        report = pilot.assess(x)
        self.assertEqual(report['consensus']['tn'], 1)
        self.assertEqual(report['field_acceptance'], 'NOT_ESTABLISHED')
        self.assertEqual(report['decision'], 'PILOT_METRICS_ONLY')
        self.assertNotIn('TECH-1', json.dumps(report))
        self.assertNotIn('TECH-2', json.dumps(report))

    def test_different_punctuation_is_not_guessed_same_person(self):
        x = ledger()
        x['reviews'][0]['reviewer_b']['id'] = 'TECH_1'
        report = pilot.assess(x)
        self.assertEqual(report['consensus']['tn'], 1)
        self.assertEqual(report['field_acceptance'], 'NOT_ESTABLISHED')


if __name__ == '__main__':
    unittest.main()
