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


class RealBoundaryChecks(unittest.TestCase):
    def test_neon_ci_recovery_query_is_owner_scoped_read_only_and_aged(self):
        calls = []
        row = (ID, BRANCH, URL, SHA)
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self, sql, args=None): calls.append((sql, args))
            def fetchone(self): return row
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def cursor(self): return Cursor()
        db = worker.NeonJobStore.__new__(worker.NeonJobStore)
        db.owner_key = OWNER
        db._connect = lambda: Connection()
        receipt = db.unverified_pr_one()
        self.assertEqual((ID, BRANCH, URL, SHA),
                         (receipt.id, receipt.branch, receipt.pr_url,
                          receipt.commit_sha))
        self.assertEqual(1, len(calls))
        sql, params = calls[0]
        self.assertEqual((OWNER,), params)
        self.assertIn("owner_key=%s", sql)
        self.assertIn("status='pr_open'", sql)
        self.assertIn("ci_run_url IS NULL", sql)
        self.assertIn("attempts=1", sql)
        self.assertIn("interval '10 minutes'", sql)
        self.assertNotIn(" UPDATE ", sql.upper())
        self.assertNotIn(" INSERT ", sql.upper())

    def test_core_ci_lookup_accepts_only_exact_branch_and_sha(self):
        gh = worker.GitHubDrafts.__new__(worker.GitHubDrafts)
        calls = []
        def request(method, route, **options):
            calls.append((method, route, options))
            return {"total_count": 1, "workflow_runs": [
                {"head_branch": BRANCH, "head_sha": SHA,
                 "event": "workflow_dispatch"}]}
        gh._request = request
        self.assertTrue(gh.core_ci_run_exists(BRANCH, SHA))
        self.assertFalse(gh.core_ci_run_exists(BRANCH, "b" * 40))
        self.assertEqual("GET", calls[0][0])
        self.assertEqual("/actions/workflows/test.yml/runs", calls[0][1])
        self.assertEqual(BRANCH, calls[0][2]["params"]["branch"])

    def test_incomplete_ci_list_does_not_permit_dispatch(self):
        gh = worker.GitHubDrafts.__new__(worker.GitHubDrafts)
        for response in (
            {}, {"total_count": 2, "workflow_runs": []},
            {"total_count": 1, "workflow_runs": [
                {"head_branch": "untrusted-branch",
                 "head_sha": SHA, "event": "workflow_dispatch"}]},
        ):
            with self.subTest(response=response):
                gh._request = lambda *_args, **_kwargs: response
                with self.assertRaises(ValueError):
                    gh.core_ci_run_exists(BRANCH, SHA)


if __name__ == "__main__":
    unittest.main()
