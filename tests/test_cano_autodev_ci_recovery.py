"""CANO draft worker must recover a lost Core CI dispatch without rerunning a model.

All GitHub, Neon and owner credentials are fake; no external calls or writes.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import cano_autodev_worker as worker

OWNER = "oidc_" + "a" * 64
ID = "12345678-1234-4123-8123-123456789abc"
BRANCH = "cano-autodev-" + ID.replace("-", "")
SHA = "a" * 40
URL = "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/123"


class DraftGithub:
    def __init__(self, *, existing=None, run_exists=False):
        self.existing = existing if existing is not None else (BRANCH, URL, SHA)
        self.run_exists = run_exists
        self.calls = []

    def find_existing_draft(self, job_id):
        self.calls.append(("find_draft", job_id))
        return self.existing

    def core_ci_run_exists(self, branch, sha):
        self.calls.append(("check_run", branch, sha))
        return self.run_exists

    def dispatch_core_ci(self, branch):
        self.calls.append(("dispatch", branch))


class RecoveryTests(unittest.TestCase):
    def receipt(self):
        return SimpleNamespace(id=ID, branch=BRANCH, pr_url=URL, commit_sha=SHA)

    def test_lost_ci_dispatch_can_be_recovered_without_recreating_draft(self):
        gh = DraftGithub()
        result = worker.recover_ci_dispatch(self.receipt(), gh)
        self.assertEqual("ci_dispatch_recovered", result)
        self.assertEqual([("find_draft", ID), ("check_run", BRANCH, SHA),
                          ("dispatch", BRANCH)], gh.calls)

    def test_existing_matching_ci_run_is_not_dispatched_twice(self):
        gh = DraftGithub(run_exists=True)
        result = worker.recover_ci_dispatch(self.receipt(), gh)
        self.assertEqual("ci_already_started", result)
        self.assertFalse(any(op[0] == "dispatch" for op in gh.calls))

    def test_mismatched_or_closed_draft_fails_closed(self):
        for value in (None, (BRANCH, URL, "b" * 40),
                      (BRANCH, "https://example.invalid", SHA)):
            gh = DraftGithub(existing=(BRANCH, URL, SHA))
            gh.existing = value
            with self.subTest(value=value):
                self.assertEqual("ci_recovery_requires_reconcile",
                                 worker.recover_ci_dispatch(self.receipt(), gh))
                self.assertEqual([("find_draft", ID)], gh.calls)

    def test_github_status_error_does_not_dispatch_or_recreate_pr(self):
        gh = DraftGithub()
        def outage(*_):
            raise RuntimeError("synthetic token-shaped private error")
        gh.core_ci_run_exists = outage
        self.assertEqual("ci_recovery_requires_reconcile",
                         worker.recover_ci_dispatch(self.receipt(), gh))
        self.assertFalse(any(op[0] == "dispatch" for op in gh.calls))

    def test_main_recovers_pr_open_before_any_new_job_claim(self):
        gh = DraftGithub()
        receipt = self.receipt()
        class FakeStore:
            claimed = False
            def verify_worker_role(self): pass
            def stale_running_one(self): return None
            def unverified_pr_one(self): return receipt
            def claim_one(self):
                self.claimed = True
                return None
        store = FakeStore()
        with patch.dict(os.environ, {
            "CANO_AUTODEV_ENABLED": "true",
            "CANO_AUTODEV_DATABASE_URL": "postgresql://synthetic.invalid/db",
            "CANO_AUTODEV_OWNER_KEY": OWNER,
            "GROQ_API_KEY": "synthetic", "GH_TOKEN": "synthetic",
            "CANO_AUTODEV_MODEL": "synthetic",
        }, clear=True), patch.object(worker, "NeonJobStore", return_value=store), \
             patch.object(worker, "GitHubDrafts", return_value=gh):
            rc = worker.main()
        self.assertEqual(0, rc)
        self.assertFalse(store.claimed)
        self.assertEqual(1, sum(op[0] == "dispatch" for op in gh.calls))


if __name__ == "__main__":
    unittest.main()
