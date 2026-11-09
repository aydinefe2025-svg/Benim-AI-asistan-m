"""Behavior-first tests: no new mutable CI dependencies without review."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_actions_ref_regressions import evaluate_policy


class WorkflowDependencyPolicyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.workflows = self.root / '.github' / 'workflows'
        self.workflows.mkdir(parents=True)
        self.baseline = {'schema': 1, 'max_movable_per_workflow': {'old.yml': 1}}

    def wf(self, name, body):
        (self.workflows/name).write_text(body, encoding='utf-8')

    def test_unchanged_legacy_workflow_is_accepted_without_lockfile(self):
        self.wf('old.yml', 'steps:\n  - uses: actions/checkout@v5\n')
        result = evaluate_policy(self.workflows, self.baseline)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['mutable_refs'], 1)

    def test_added_mutable_reference_in_existing_workflow_is_blocked(self):
        self.wf('old.yml', 'steps:\n  - uses: actions/checkout@v5\n  - uses: actions/setup-python@v6\n')
        result = evaluate_policy(self.workflows, self.baseline)
        self.assertFalse(result['ok'])
        self.assertIn('old.yml', str(result['violations']))

    def test_new_workflow_requires_sha_pinned_actions(self):
        self.wf('old.yml', 'steps:\n  - uses: actions/checkout@v5\n')
        self.wf('new.yaml', 'steps:\n  - uses: actions/checkout@v5\n')
        self.assertFalse(evaluate_policy(self.workflows, self.baseline)['ok'])
        self.wf('new.yaml', 'steps:\n  - uses: actions/checkout@'+'a'*40+'\n')
        result = evaluate_policy(self.workflows, self.baseline)
        self.assertTrue(result['ok'], result)

    def test_new_local_and_exact_sha_actions_are_not_mutable_remote_references(self):
        self.wf('old.yml', 'steps:\n  - uses: ./.github/actions/local\n  - uses: actions/setup-python@'+'b'*40+'\n')
        result = evaluate_policy(self.workflows, self.baseline)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['mutable_refs'], 0)

    def test_unrecognized_dynamic_action_fails_closed(self):
        self.wf('old.yml', 'steps:\n  - uses: ${{ env.DYNAMIC_ACTION }}\n')
        self.assertFalse(evaluate_policy(self.workflows, self.baseline)['ok'])

    def test_pull_request_target_requires_security_review_even_without_actions(self):
        self.wf('old.yml', 'on:\n  pull_request_target:\nsteps:\n  - run: echo safe\n')
        self.assertFalse(evaluate_policy(self.workflows, self.baseline)['ok'])

    def test_commented_out_actions_are_ignored(self):
        self.wf('old.yml', '# - uses: unsafe/thing@latest\nsteps:\n  - uses: "actions/checkout@v5" # comment\n')
        result = evaluate_policy(self.workflows, self.baseline)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['mutable_refs'], 1)

    def test_bad_baseline_rejected_instead_of_loosening_policy(self):
        self.wf('old.yml', 'steps:\n  - uses: actions/checkout@v5\n')
        broken = {'schema': 1, 'max_movable_per_workflow': {'old.yml': -1}}
        with self.assertRaises(ValueError):
            evaluate_policy(self.workflows, broken)

    def test_missing_directory_is_not_reported_green(self):
        with self.assertRaises(FileNotFoundError):
            evaluate_policy(self.root/'absent', self.baseline)


if __name__ == '__main__':
    unittest.main()