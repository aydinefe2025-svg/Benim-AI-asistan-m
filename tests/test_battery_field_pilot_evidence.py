"""Synthetic field technician/metadata cases, never customer measurements."""
import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'battery_curve_audit'))
import field_pilot_evidence as pilot


def fixture():
    return {
        'schema': 'cano.battery.field-pilot.v1',
        'audit_receipt_sha256': 'a' * 64,
        'site_authorization': {'permitted': True, 'reference': 'PILOT-APPROVAL-123'},
        'cells': [
            {'cell': 'A-PRIVATE', 'device': 'D1', 'batch': 'B1', 'campaign': 'C1'},
            {'cell': 'B-PRIVATE', 'device': 'D2', 'batch': 'B2', 'campaign': 'C2'},
            {'cell': 'C-PRIVATE', 'device': 'D3', 'batch': 'B3', 'campaign': 'C3'},
            {'cell': 'D-PRIVATE', 'device': 'D4', 'batch': 'B4', 'campaign': 'C4'},
        ],
        'assignments': [
            {'cell': 'A-PRIVATE', 'partition': 'train'},
            {'cell': 'B-PRIVATE', 'partition': 'validation'},
            {'cell': 'C-PRIVATE', 'partition': 'test'},
            {'cell': 'D-PRIVATE', 'partition': 'train'},
        ],
        'screened_pair_count': 6, 'screened_flagged_count': 2,
        'reviews': [
            {'a': 'A-PRIVATE', 'b': 'B-PRIVATE', 'flagged': True,
             'reviewer_a': {'id': 'tech-1', 'verdict': 'linked'},
             'reviewer_b': {'id': 'tech-2', 'verdict': 'linked'}},
            {'a': 'A-PRIVATE', 'b': 'C-PRIVATE', 'flagged': False,
             'reviewer_a': {'id': 'tech-1', 'verdict': 'linked'},
             'reviewer_b': {'id': 'tech-2', 'verdict': 'linked'}},
            {'a': 'A-PRIVATE', 'b': 'D-PRIVATE', 'flagged': True,
             'reviewer_a': {'id': 'tech-1', 'verdict': 'independent'},
             'reviewer_b': {'id': 'tech-2', 'verdict': 'independent'}},
            {'a': 'B-PRIVATE', 'b': 'C-PRIVATE', 'flagged': False,
             'reviewer_a': {'id': 'tech-1', 'verdict': 'independent'},
             'reviewer_b': {'id': 'tech-2', 'verdict': 'independent'}},
        ],
    }


class FieldPilotTests(unittest.TestCase):
    def test_disagreement_and_missing_labels_never_become_ground_truth(self):
        x = fixture()
        x['reviews'][3]['reviewer_b']['verdict'] = 'linked'
        x['reviews'][2]['reviewer_b']['verdict'] = 'unknown'
        report = pilot.assess(x)
        self.assertEqual(report['consensus'], {'tp': 1, 'fp': 0, 'fn': 1, 'tn': 0})
        self.assertEqual(report['disagreements'], 1)
        self.assertEqual(report['unresolved'], 1)
        self.assertEqual(report['field_acceptance'], 'NOT_ESTABLISHED')
        self.assertIsNone(report['rates']['specificity'])

    def test_consensus_metrics_are_observed_subset_not_claimed_population_truth(self):
        report = pilot.assess(fixture())
        self.assertEqual(report['consensus'], {'tp': 1, 'fp': 1, 'fn': 1, 'tn': 1})
        self.assertEqual(report['rates']['precision'], 0.5)
        self.assertEqual(report['rates']['recall'], 0.5)
        self.assertEqual(report['reviewed_pair_count'], 4)
        self.assertEqual(report['screened_pair_count'], 6)
        self.assertFalse(report['full_frame_reviewed'])
        self.assertEqual(report['field_acceptance'], 'NOT_ESTABLISHED')

    def test_same_device_across_split_blocks_provenance(self):
        x = fixture()
        x['cells'][1]['device'] = 'D1'
        report = pilot.assess(x)
        self.assertEqual(report['decision'], 'BLOCK_PROVENANCE_LEAKAGE')
        self.assertGreater(report['cross_split_metadata_links'], 0)
        self.assertFalse(report['provenance_group_holdout_valid'])

    def test_shared_batch_and_campaign_both_enforce_grouping(self):
        x = fixture()
        x['cells'][1]['batch'] = x['cells'][0]['batch']
        x['cells'][2]['campaign'] = x['cells'][0]['campaign']
        report = pilot.assess(x)
        self.assertEqual(report['decision'], 'BLOCK_PROVENANCE_LEAKAGE')
        self.assertEqual(report['provenance_connected_groups'], 2)

    def test_same_device_and_batch_within_same_partition_not_cross_split(self):
        x = fixture()
        x['cells'][3]['device'] = x['cells'][0]['device']
        x['cells'][3]['batch'] = x['cells'][0]['batch']
        for record in x['reviews']:
            record['reviewer_a']['verdict'] = 'independent'
            record['reviewer_b']['verdict'] = 'independent'
        report = pilot.assess(x)
        self.assertTrue(report['provenance_group_holdout_valid'])
        self.assertEqual(report['provenance_connected_groups'], 3)
        self.assertEqual(report['decision'], 'PILOT_METRICS_ONLY')

    def test_missing_metadata_and_unmapped_cells_fail_closed(self):
        x = fixture()
        del x['cells'][1]['campaign']
        with self.assertRaisesRegex(ValueError, 'campaign|metadata'):
            pilot.assess(x)
        x = fixture()
        del x['assignments'][-1]
        with self.assertRaisesRegex(ValueError, 'assignments'):
            pilot.assess(x)

    def test_reversed_duplicate_review_pair_fails_closed(self):
        x = fixture()
        r = copy.deepcopy(x['reviews'][0])
        r['a'], r['b'] = r['b'], r['a']
        x['reviews'].append(r)
        with self.assertRaisesRegex(ValueError, 'duplicate.*pair'):
            pilot.assess(x)

    def test_cannot_use_same_reviewer_twice(self):
        x = fixture()
        x['reviews'][0]['reviewer_b']['id'] = 'tech-1'
        with self.assertRaisesRegex(ValueError, 'reviewer'):
            pilot.assess(x)

    def test_undefined_rate_is_null_not_zero(self):
        x = fixture()
        x['reviews'] = x['reviews'][:1]
        x['screened_pair_count'] = 1
        x['screened_flagged_count'] = 1
        report = pilot.assess(x)
        self.assertIsNone(report['rates']['specificity'])
        self.assertEqual(report['rates']['false_negative_rate'], 0.0)
        x = fixture()
        x['reviews'] = [x['reviews'][2]]
        x['screened_pair_count'] = 1
        x['screened_flagged_count'] = 1
        report = pilot.assess(x)
        self.assertIsNone(report['rates']['false_negative_rate'])
        self.assertIsNone(report['rates']['recall'])

    def test_full_frame_count_is_conditional_on_both_flags_and_coverage(self):
        x = fixture()
        x['screened_pair_count'] = 4
        x['screened_flagged_count'] = 2
        report = pilot.assess(x)
        self.assertTrue(report['full_frame_reviewed'])
        self.assertEqual(report['field_acceptance'], 'NOT_ESTABLISHED')
        x['screened_flagged_count'] = 3
        with self.assertRaisesRegex(ValueError, 'flagged.*frame'):
            pilot.assess(x)

    def test_public_summary_contains_no_identifiers_receipts_or_human_ids(self):
        report = pilot.assess(fixture())
        text = json.dumps(report)
        for secret in ['A-PRIVATE', 'B-PRIVATE', 'PILOT-APPROVAL', 'tech-1', 'D1', 'B1', 'C1', 'a'*64]:
            self.assertNotIn(secret, text)

    def test_cli_rejects_replacement_and_never_modifies_input(self):
        x = fixture()
        for review in x['reviews']:
            review['reviewer_a']['verdict'] = 'independent'
            review['reviewer_b']['verdict'] = 'independent'
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ledger = root/'ledger.json'
            ledger.write_text(json.dumps(x), encoding='utf-8')
            raw = ledger.read_bytes()
            output = root/'summary.json'
            cmd = [sys.executable, str(Path(pilot.__file__)), '--ledger', str(ledger), '--summary', str(output)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(output.exists())
            if os.name == 'posix':
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            proc2 = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc2.returncode, 2)
            self.assertEqual(ledger.read_bytes(), raw)
            overlap = subprocess.run([sys.executable, str(Path(pilot.__file__)), '--ledger', str(ledger), '--summary', str(ledger)],capture_output=True,text=True)
            self.assertEqual(overlap.returncode, 2)
            self.assertEqual(ledger.read_bytes(), raw)

    def test_technician_consensus_link_across_splits_blocks_even_with_unique_devices(self):
        x = fixture()
        report = pilot.assess(x)
        self.assertEqual(report['cross_split_metadata_links'], 0)
        self.assertGreater(report['cross_split_technician_consensus_links'], 0)
        self.assertEqual(report['decision'], 'BLOCK_PROVENANCE_LEAKAGE')

    def test_cli_returns_nonzero_for_leak_but_keeps_private_input_intact(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ledger = root / 'ledger.json'
            ledger.write_text(json.dumps(fixture()), encoding='utf-8')
            source = ledger.read_bytes()
            output = root / 'summary.json'
            proc = subprocess.run([sys.executable, str(Path(pilot.__file__)),
                '--ledger', str(ledger), '--summary', str(output)],capture_output=True,text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(ledger.read_bytes(), source)
            report = json.loads(output.read_text())
            self.assertEqual(report['decision'], 'BLOCK_PROVENANCE_LEAKAGE')
            self.assertNotIn('A-PRIVATE', output.read_text())

    def test_invalid_authorization_and_receipt_block(self):
        x = fixture()
        x['site_authorization']['permitted'] = False
        with self.assertRaisesRegex(ValueError, 'authorization'):
            pilot.assess(x)
        x = fixture()
        x['audit_receipt_sha256'] = 'bad'
        with self.assertRaisesRegex(ValueError, 'receipt'):
            pilot.assess(x)


if __name__ == '__main__':
    unittest.main()
