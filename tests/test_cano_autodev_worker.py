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
