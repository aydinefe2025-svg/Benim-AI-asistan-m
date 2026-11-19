"""Synthetic reviewer alias adversarial simulations; no actual technicians."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'battery_curve_audit'))
import reviewer_identity_lab as lab


class ReviewerIdentityLabTests(unittest.TestCase):
    def test_repeatable_50_alias_and_distinct_controls(self):
        result = lab.run_all(trials=5, seed=1024)
        self.assertEqual(result['total_cases'], 50)
        self.assertEqual(result['alias_cases'], 30)
        self.assertEqual(result['same_person_label_alias_rejected'], 30)
        self.assertEqual(result['alias_escapes'], 0)
        self.assertEqual(result['distinct_text_control_cases'], 20)
        self.assertEqual(result['distinct_text_controls_not_rejected'], 20)
        self.assertFalse(result['reviewer_independence_cryptographically_verified'])

    def test_seed_reproduces_same_evidence_without_identifying_names(self):
        a = lab.run_all(trials=3, seed=20261119)
        b = lab.run_all(trials=3, seed=20261119)
        self.assertEqual(a, b)
        self.assertNotIn('TECH-', json.dumps(a))
        self.assertEqual(a['total_cases'], 30)

    def test_bad_trial_numbers_and_seed_fail_closed(self):
        for trials in (0, 1001, True, -1):
            with self.subTest(trials=trials), self.assertRaises(ValueError):
                lab.run_all(trials=trials)
        with self.assertRaises(ValueError):
            lab.run_all(seed=-1)

    def test_output_is_written_once_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'result.json'
            self.assertEqual(lab.main(['--trials', '2', '--output', str(target)]), 0)
            before = target.read_bytes()
            self.assertEqual(json.loads(before)['total_cases'], 20)
            with self.assertRaises(FileExistsError):
                lab.main(['--trials', '2', '--output', str(target)])
            self.assertEqual(target.read_bytes(), before)
            if os.name == 'posix':
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)


if __name__ == '__main__':
    unittest.main()
