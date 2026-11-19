"""CANO scheduled draft-PR worker safety and lifecycle contracts."""
import unittest

from scripts.cano_autodev_worker import (
    extract_target, validate_candidate, process_job, Job,
)


SOURCE = "def greeting():\n    return 'old'\n"
REWRITE = "def greeting():\n    return 'new'\n"


class FakeDatabase:
    def __init__(self):
        self.completed = []
        self.blocked = []

    def record_pr(self, job_id, branch, pr_url, commit):
        self.completed.append((job_id, branch, pr_url, commit))

    def block(self, job_id, reason):
        self.blocked.append((job_id, reason))


class FakeGitHub:
    def __init__(self):
        self.calls = []

    def fetch(self, path):
        self.calls.append(("fetch", path))
        return SOURCE, "source-sha"

    def dispatch_core_ci(self, branch):
        self.calls.append(("ci", branch))

    def create_draft(self, job_id, path, source_sha, candidate, goal):
        self.calls.append(("draft", path, candidate))
        return "cano-autodev-" + job_id, "https://github.com/test/pr/3", "commitsha"


class FakeModel:
    def __init__(self, response=REWRITE):
        self.response = response
        self.calls = []

    def rewrite(self, goal, path, source):
        self.calls.append((goal, path))
        return self.response


class WorkerTests(unittest.TestCase):
    def test_goal_requires_explicit_bounded_core_python_path(self):
        self.assertEqual(
            extract_target("Fix core/cano_development_status.py count"),
            "core/cano_development_status.py",
        )
        for goal in (
            "Improve CANO automatically", "Edit ../core/status.py",
            "Edit .github/workflows/bot.yml", "Edit core/auth_login.py",
            "Edit tests/test_x.py", "Edit core/foo.py/../safe.py",
        ):
            with self.subTest(goal=goal):
                self.assertIsNone(extract_target(goal))

    def test_safe_syntax_correct_fix_is_accepted(self):
        self.assertEqual(validate_candidate(SOURCE, REWRITE), REWRITE)

    def test_dangerous_or_unreviewable_change_fails_closed(self):
        invalid = (
            SOURCE,
            "def greeting(:\n    pass\n",
            "import os\n" + REWRITE,
            "def greeting():\n    return eval('1+2')\n",
            "def greeting():\n    return open('/tmp/x').read()\n",
            "def greeting():\n    return 'x'\n" * 300,
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate[:30]), self.assertRaises(ValueError):
                validate_candidate(SOURCE, candidate)

    def test_one_job_creates_a_draft_only_and_records_receipt(self):
        db, github, model = FakeDatabase(), FakeGitHub(), FakeModel()
        job = Job("12345678", "Fix core/cano_development_status.py greeting")
        outcome = process_job(job, db, github, model)
        self.assertEqual(outcome, "pr_open")
        self.assertEqual(db.completed[0][1], "cano-autodev-12345678")
        self.assertEqual(len([x for x in github.calls if x[0] == "draft"]), 1)
        self.assertFalse(db.blocked)

    def test_missing_path_blocks_without_model_or_github_calls(self):
        db, github, model = FakeDatabase(), FakeGitHub(), FakeModel()
        outcome = process_job(Job("job1", "Please improve all code"), db, github, model)
        self.assertEqual(outcome, "blocked")
        self.assertEqual(db.blocked, [("job1", "missing_safe_target")])
        self.assertFalse(github.calls)
        self.assertFalse(model.calls)

    def test_invalid_generated_code_never_reaches_github_write(self):
        db, github, model = FakeDatabase(), FakeGitHub(), FakeModel(
            "import subprocess\n" + REWRITE)
        outcome = process_job(Job("job2", "Fix core/cano_development_status.py"), db, github, model)
        self.assertEqual(outcome, "blocked")
        self.assertEqual(db.blocked, [("job2", "unsafe_candidate")])
        self.assertFalse(any(x[0] == "draft" for x in github.calls))


class FakePGCursor:
    def __init__(self, row=None):
        self.row = row
        self.queries = []
        self.rowcount = 1

    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params=None): self.queries.append((sql, params))
    def fetchone(self): return self.row


class FakePGConnection:
    def __init__(self, cursor): self.cursor_value = cursor
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return self.cursor_value


class IntegrationBoundaryTests(unittest.TestCase):
    def test_claim_is_one_atomic_non_retrying_locked_job(self):
        from scripts.cano_autodev_worker import NeonJobStore
        cursor = FakePGCursor(("example-id", "Fix core/cano_development_status.py"))
        store = NeonJobStore.__new__(NeonJobStore)
        store._connect = lambda: FakePGConnection(cursor)
        store.owner_key = "oidc_" + "a"*64
        job = store.claim_one()
        self.assertEqual(job.id, "example-id")
        statement = cursor.queries[0][0]
        self.assertIn("FOR UPDATE SKIP LOCKED", statement)
        self.assertIn("attempts=0", statement)
        self.assertIn("LIMIT 1", statement)
        self.assertIn("RETURNING j.id::text,j.goal", statement)
        self.assertIn("owner_key=%s", statement)

    def test_draft_pr_never_includes_private_goal_text(self):
        from scripts.cano_autodev_worker import GitHubDrafts
        request_log = []
        api = GitHubDrafts.__new__(GitHubDrafts)

        def request(method, path, **options):
            request_log.append((method, path, options))
            if path.endswith("/git/ref/heads/main"):
                return {"object": {"sha": "mainsha"}}
            if path.endswith("/contents/core/safe.py"):
                return {"commit": {"sha": "newsha"}}
            if path.endswith("/pulls"):
                return {"html_url": "https://github.com/example/pull/7"}
            return {}
        api._request = request
        uid = "12345678-1234-4123-8123-123456789abc"
        private_goal = "Fix core/safe.py; confidential meeting identifier 24680"
        branch, url, sha = api.create_draft(
            uid, "core/safe.py", "blobsha", REWRITE, private_goal)
        self.assertEqual(sha, "newsha")
        self.assertEqual(url, "https://github.com/example/pull/7")
        self.assertTrue(branch.startswith("cano-autodev-"))
        pull = request_log[-1][2]["json"]
        self.assertTrue(pull["draft"])
        self.assertNotIn("24680", pull["body"])
        self.assertNotIn("24680", pull["title"])

    def test_disabled_worker_does_not_touch_database_or_model(self):
        from scripts.cano_autodev_worker import main
        from unittest.mock import patch
        with patch.dict("os.environ", {"CANO_AUTODEV_ENABLED": "false"}):
            self.assertEqual(main(), 0)


if __name__ == "__main__":
    unittest.main()


class OwnerIsolationAndCITests(unittest.TestCase):
    """Regression cases for the second, independently-reviewed worker gate."""

    def test_owner_scope_is_mandatory_for_claim_and_transitions(self):
        from scripts.cano_autodev_worker import NeonJobStore
        owner = "oidc_" + "a" * 64
        cursor = FakePGCursor(("example-id", "Fix core/cano_development_status.py"))
        store = NeonJobStore.__new__(NeonJobStore)
        store.owner_key = owner
        store._connect = lambda: FakePGConnection(cursor)
        store.claim_one()
        self.assertIn("owner_key=%s", cursor.queries[0][0])
        self.assertIn(owner, cursor.queries[0][1])
        cursor.queries.clear()
        store.record_pr("example-id", "branch", "https://github.com/example/pr/3", "sha")
        self.assertIn("owner_key=%s", cursor.queries[0][0])
        self.assertIn(owner, cursor.queries[0][1])
        cursor.queries.clear()
        store.block("example-id", "unsafe_candidate")
        self.assertIn("owner_key=%s", cursor.queries[0][0])
        self.assertIn(owner, cursor.queries[0][1])

    def test_invalid_owner_key_is_rejected_before_connecting(self):
        from scripts.cano_autodev_worker import NeonJobStore
        with self.assertRaises(PermissionError):
            NeonJobStore("postgresql://example.invalid/db", "oidc_wrong")

    def test_missing_owner_key_fails_closed_in_main(self):
        from scripts.cano_autodev_worker import main
        from unittest.mock import patch
        with patch.dict("os.environ", {
            "CANO_AUTODEV_ENABLED": "true", "CANO_AUTODEV_DATABASE_URL": "postgresql://example.invalid/db",
            "GROQ_API_KEY": "dummy", "GH_TOKEN": "dummy", "CANO_AUTODEV_MODEL": "dummy",
        }, clear=True):
            self.assertEqual(main(), 1)

    def test_pr_open_dispatches_core_ci_explicitly(self):
        db, github, model = FakeDatabase(), FakeGitHub(), FakeModel()
        github.dispatched = []
        github.dispatch_core_ci = github.dispatched.append
        result = process_job(Job("12345678", "Fix core/cano_development_status.py"), db, github, model)
        self.assertEqual(result, "pr_open")
        self.assertEqual(github.dispatched, [db.completed[0][1]])

    def test_ci_dispatch_failure_never_erases_existing_pr_receipt(self):
        db, github, model = FakeDatabase(), FakeGitHub(), FakeModel()
        def fail_dispatch(branch):
            raise RuntimeError("provider response must not be logged")
        github.dispatch_core_ci = fail_dispatch
        result = process_job(Job("12345678", "Fix core/cano_development_status.py"), db, github, model)
        self.assertEqual(result, "pr_open_ci_dispatch_failed")
        self.assertEqual(len(db.completed), 1)
        self.assertEqual(db.blocked, [])

    def test_github_accepts_empty_204_dispatch_response(self):
        from scripts.cano_autodev_worker import GitHubDrafts
        api = GitHubDrafts.__new__(GitHubDrafts)
        class FakeResponse:
            content = b""
            def raise_for_status(self): pass
            def json(self): raise AssertionError("No JSON to parse for HTTP 204")
        class FakeSession:
            def request(self, method, url, **kwargs):
                return FakeResponse()
        api._session = FakeSession()
        api._base = "https://api.github.com/repos/aydinefe2025-svg/Benim-AI-asistan-m"
        self.assertEqual(api.dispatch_core_ci("cano-autodev-" + "a"*32), None)



class WorkerCredentialGuardTests(unittest.TestCase):
    """Administrative Neon credentials must never run the unattended code worker."""

    def store(self, role_row, rls_row=(True, False)):
        from scripts.cano_autodev_worker import NeonJobStore
        class GuardCursor(FakePGCursor):
            def fetchone(self):
                sql = self.queries[-1][0]
                if 'FROM pg_roles' in sql:
                    return role_row
                if 'FROM pg_class' in sql:
                    return rls_row
                return super().fetchone()
        cur = GuardCursor()
        store = NeonJobStore.__new__(NeonJobStore)
        store.owner_key = 'oidc_' + 'a'*64
        store._connect = lambda: FakePGConnection(cur)
        return store, cur

    def test_reject_admin_and_any_unexpected_worker_role(self):
        for roles in [
            ('assistant_owner', True, False),
            ('agent_task_app', False, False),
            ('cano_autodev_worker', True, False),
            ('cano_autodev_worker', False, True),
            None,
        ]:
            with self.subTest(role=roles), self.assertRaises(PermissionError):
                store, _ = self.store(roles)
                store.verify_worker_role()

    def test_reject_worker_if_table_rls_is_disabled(self):
        store, _ = self.store(('cano_autodev_worker', False, False), (False, False))
        with self.assertRaises(PermissionError):
            store.verify_worker_role()

    def test_accepts_only_rls_enforced_worker_and_queries_metadata(self):
        store, cur = self.store(('cano_autodev_worker', False, False), (True, False))
        store.verify_worker_role()
        self.assertEqual(len(cur.queries), 2)
        self.assertIn('FROM pg_roles', cur.queries[0][0])
        self.assertIn('FROM pg_class', cur.queries[1][0])



class InterruptedDraftRecoveryTests(unittest.TestCase):
    """A created GitHub PR must not disappear from the Neon acceptance trail."""

    def test_failed_receipt_write_does_not_mark_a_real_pr_as_blocked(self):
        class BrokenReceipt(FakeDatabase):
            def record_pr(self, job_id, branch, pr_url, commit):
                raise RuntimeError("db temporarily unavailable")
        db, github = BrokenReceipt(), FakeGitHub()
        outcome = process_job(
            Job("12345678", "Fix core/cano_development_status.py count"),
            db, github, FakeModel())
        self.assertEqual(outcome, "pr_receipt_needs_reconcile")
        self.assertEqual(db.blocked, [])
        self.assertEqual(len([x for x in github.calls if x[0] == "draft"]), 1)

    def test_stale_running_job_is_owner_scoped_and_never_reclaimed_for_reexecution(self):
        from scripts.cano_autodev_worker import NeonJobStore
        cursor = FakePGCursor(("12345678-1234-4123-8123-123456789abc", "Fix core/safe.py"))
        store = NeonJobStore.__new__(NeonJobStore)
        store.owner_key = "oidc_" + "a" * 64
        store._connect = lambda: FakePGConnection(cursor)
        job = store.stale_running_one()
        self.assertEqual(job.id, "12345678-1234-4123-8123-123456789abc")
        statement, args = cursor.queries[0]
        self.assertIn("owner_key=%s", statement)
        self.assertIn("attempts=1", statement)
        self.assertIn("pr_url IS NULL", statement)
        self.assertIn("FOR UPDATE SKIP LOCKED", statement)
        self.assertEqual(args, (store.owner_key,))

    def test_verified_existing_draft_restores_receipt_without_any_model_call(self):
        from scripts.cano_autodev_worker import reconcile_job
        job = Job("12345678-1234-4123-8123-123456789abc", "Fix core/safe.py")
        db, github = FakeDatabase(), FakeGitHub()
        branch = "cano-autodev-" + job.id.replace("-", "")
        github.find_existing_draft = lambda job_id: (branch, "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/999", "a"*40)
        result = reconcile_job(job, db, github)
        self.assertEqual(result, "pr_open")
        self.assertEqual(len(db.completed), 1)
        self.assertEqual(db.completed[0][1], branch)
        self.assertEqual(len([x for x in github.calls if x[0] == "ci"]), 1)

    def test_missing_draft_never_reexecutes_or_blocks_stale_job(self):
        from scripts.cano_autodev_worker import reconcile_job
        db, github = FakeDatabase(), FakeGitHub()
        github.find_existing_draft = lambda job_id: None
        result = reconcile_job(Job("12345678-1234-4123-8123-123456789abc", "Fix core/safe.py"), db, github)
        self.assertEqual(result, "recovery_requires_reconcile")
        self.assertFalse(db.completed)
        self.assertFalse(db.blocked)
        self.assertEqual(github.calls, [])

    def test_existing_draft_must_match_repository_branch_base_and_open_draft(self):
        from scripts.cano_autodev_worker import GitHubDrafts
        api = GitHubDrafts.__new__(GitHubDrafts)
        job_id = "12345678-1234-4123-8123-123456789abc"
        branch = "cano-autodev-" + job_id.replace("-", "")
        valid = {
            "state": "open", "draft": True,
            "html_url": "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/999",
            "head": {"ref": branch, "sha": "a"*40,
                     "repo": {"full_name": "aydinefe2025-svg/Benim-AI-asistan-m"}},
            "base": {"ref": "main"},
        }
        api._request = lambda method, path, **options: [valid]
        self.assertEqual(api.find_existing_draft(job_id), (branch, valid["html_url"], "a"*40))
        for edit in (
            {"draft": False},
            {"base": {"ref": "dev"}},
            {"head": {"ref": "other", "sha": "a"*40, "repo": {"full_name": "aydinefe2025-svg/Benim-AI-asistan-m"}}},
            {"html_url": "https://attacker.invalid/pull/999"},
        ):
            bad = dict(valid, **edit)
            api._request = lambda method, path, **options: [bad]
            self.assertIsNone(api.find_existing_draft(job_id))



class StaleUnwrittenJobRecoveryTests(unittest.TestCase):
    """An interrupted no-branch job must not starve later owner tasks."""

    def test_old_job_without_github_branch_is_blocked_without_replay(self):
        from scripts.cano_autodev_worker import reconcile_job
        job = Job("12345678-1234-4123-8123-123456789abc", "Fix core/safe.py")
        db, github = FakeDatabase(), FakeGitHub()
        github.find_existing_draft = lambda job_id: None
        github.branch_exists = lambda job_id: False
        result = reconcile_job(job, db, github)
        self.assertEqual(result, "stale_without_branch_blocked")
        self.assertEqual(db.blocked, [(job.id, "interrupted_no_github_branch")])
        self.assertFalse(db.completed)
        self.assertFalse(github.calls)

    def test_existing_branch_without_pr_is_never_discarded(self):
        from scripts.cano_autodev_worker import reconcile_job
        job = Job("12345678-1234-4123-8123-123456789abc", "Fix core/safe.py")
        db, github = FakeDatabase(), FakeGitHub()
        github.find_existing_draft = lambda job_id: None
        github.branch_exists = lambda job_id: True
        self.assertEqual(reconcile_job(job, db, github), "recovery_requires_reconcile")
        self.assertEqual(db.blocked, [])

    def test_failed_github_branch_lookup_fails_closed(self):
        from scripts.cano_autodev_worker import reconcile_job
        db, github = FakeDatabase(), FakeGitHub()
        github.find_existing_draft = lambda job_id: None
        github.branch_exists = lambda job_id: (_ for _ in ()).throw(
            RuntimeError("GitHub not reachable"))
        self.assertEqual(reconcile_job(
            Job("12345678-1234-4123-8123-123456789abc", "Fix core/safe.py"),
            db, github), "recovery_unavailable")
        self.assertEqual(db.blocked, [])

    def test_github_only_404_confirms_absent_branch(self):
        from scripts.cano_autodev_worker import GitHubDrafts
        api = GitHubDrafts.__new__(GitHubDrafts)
        uid = "12345678-1234-4123-8123-123456789abc"
        class FakeHTTPError(Exception):
            def __init__(self, code):
                self.response = type("Response", (), {"status_code": code})()
        api._request = lambda *args, **kwargs: (_ for _ in ()).throw(FakeHTTPError(404))
        self.assertIs(api.branch_exists(uid), False)
        api._request = lambda *args, **kwargs: (_ for _ in ()).throw(FakeHTTPError(403))
        with self.assertRaises(FakeHTTPError):
            api.branch_exists(uid)
        api._request = lambda *args, **kwargs: {"ref": "refs/heads/cano-autodev"}
        self.assertIs(api.branch_exists(uid), True)

    def test_after_verified_no_branch_stale_is_blocked_next_queued_job_may_run(self):
        from scripts.cano_autodev_worker import main
        from unittest.mock import patch, MagicMock
        old = Job("12345678-1234-4123-8123-123456789abc", "Fix core/safe.py")
        new = Job("87654321-1234-4123-8123-123456789abc", "Fix core/next.py")
        db = MagicMock()
        db.stale_running_one.return_value = old
        db.claim_one.return_value = new
        with patch.dict("os.environ", {
            "CANO_AUTODEV_ENABLED": "true",
            "CANO_AUTODEV_DATABASE_URL": "postgresql://example.invalid/db",
            "GROQ_API_KEY": "placeholder", "GH_TOKEN": "placeholder",
            "CANO_AUTODEV_MODEL": "placeholder",
            "CANO_AUTODEV_OWNER_KEY": "oidc_" + "a" * 64
        }, clear=True), patch("scripts.cano_autodev_worker.NeonJobStore", return_value=db), \
             patch("scripts.cano_autodev_worker.GitHubDrafts"), \
             patch("scripts.cano_autodev_worker.GroqRewriteModel"), \
             patch("scripts.cano_autodev_worker.reconcile_job",
                   return_value="stale_without_branch_blocked"), \
             patch("scripts.cano_autodev_worker.process_job", return_value="pr_open") as process:
            self.assertEqual(main(), 0)
            db.claim_one.assert_called_once_with()
            process.assert_called_once()
            self.assertEqual(process.call_args.args[0], new)
