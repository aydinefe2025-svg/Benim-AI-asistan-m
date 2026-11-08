"""Behavioral proof of the existing composition holdout's ceiling/floor censoring.

The study is retrospective, never presented as a prospective adaptation test.
"""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from organism_lab.holdout_censoring_audit import (
    EXPECTED_BODY_SHA256, audit_reports, verify_archived_report, save_audit,
)

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / 'research_reports' / 'organism-lab-transfer'
FILES = [DATA / name for name in EXPECTED_BODY_SHA256]


class ForensicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = audit_reports(FILES)

    def test_90_seed_pairs_and_450_original_simulations(self):
        result = self.result
        self.assertEqual(result['source_simulations'], 450)
        self.assertEqual(result['paired_seeds'], 90)
        self.assertEqual(len(result['cohorts']), 3)
        self.assertEqual(len(result['per_seed']), 90)

    def test_ceiling_floor_explain_most_population_ties(self):
        result = self.result['pooled']
        self.assertEqual(result['final_population_ties'], 87)
        self.assertEqual(result['both_at_capacity'], 65)
        self.assertEqual(result['both_at_floor'], 19)
        self.assertEqual(result['other_ties'], 3)
        self.assertEqual(result['task_share_gain_hidden_by_population_tie'], 55)

    def test_retained_distinct_growth_metrics_and_tradeoff(self):
        r = self.result['pooled']
        self.assertEqual(r['positive_task_share'], 58)
        self.assertEqual(r['negative_task_share'], 5)
        self.assertEqual(r['tied_task_share'], 27)
        self.assertAlmostEqual(r['rewarded_step_delta']['mean'], 30.0777777778)
        self.assertAlmostEqual(r['births_added_delta']['mean'], -1.4777777778)
        self.assertAlmostEqual(r['final_population_delta']['mean'], 1.2111111111)
        self.assertLess(r['rewarded_step_delta']['ci95_low'], r['rewarded_step_delta']['mean'])
        self.assertLess(r['births_added_delta']['ci95_high'], 0)
        self.assertFalse(self.result['adaptation_proven'])

    def test_all_cohorts_obey_known_counts(self):
        rows = self.result['cohorts']
        self.assertEqual([r['both_at_capacity'] for r in rows], [22, 23, 20])
        self.assertEqual([r['final_population_ties'] for r in rows], [30, 29, 28])
        self.assertEqual([r['positive_task_share'] for r in rows], [19, 20, 19])

    def test_reject_modified_report_even_when_digest_is_recomputed(self):
        original = json.loads(FILES[0].read_text())
        tampered = copy.deepcopy(original)
        tampered['report']['trials'][0]['composition_holdout']['population'] = 999
        tampered['sha256'] = hashlib.sha256((json.dumps(tampered['report'], sort_keys=True, separators=(',', ':'), ensure_ascii=False)+'\n').encode()).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / FILES[0].name
            path.write_text(json.dumps(tampered), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'pinned source hash'):
                verify_archived_report(path)

    def test_reject_duplicate_seed_or_missing_control(self):
        original = json.loads(FILES[0].read_text())
        for field in ('duplicate', 'missing_control'):
            changed = copy.deepcopy(original)
            if field == 'duplicate':
                changed['report']['trials'][5]['seed'] = changed['report']['trials'][0]['seed']
            else:
                changed['report']['trials'] = [x for x in changed['report']['trials'] if not (x['seed'] == 0 and x['arm'] == 'no_division')]
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / FILES[0].name
                path.write_text(json.dumps(changed), encoding='utf-8')
                with self.assertRaises(ValueError):
                    audit_reports([path, *FILES[1:]], check_pins=False)

    def test_save_and_verify_idempotence_and_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'audit.json'
            original = save_audit(self.result, target)
            by = target.read_bytes()
            self.assertEqual(save_audit(self.result, target), original)
            self.assertEqual(target.read_bytes(), by)
            changed = copy.deepcopy(self.result)
            changed['adaptation_proven'] = True
            with self.assertRaises(FileExistsError):
                save_audit(changed, target)
            self.assertEqual(target.read_bytes(), by)

    def test_metadata_explicitly_retrospective(self):
        self.assertEqual(self.result['classification'], 'posthoc_forensic_not_new_experiment')
        self.assertIn('not', self.result['interpretation'].lower())
        self.assertEqual(len(self.result['input_body_sha256']), 3)

if __name__ == '__main__':
    unittest.main()
