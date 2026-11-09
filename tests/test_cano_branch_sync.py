"""Integration acceptance for safe main-to-Render Git ref synchronization."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from core import continuous_colony  # Confirms merged CANO source remains importable.
from scripts.cano_safe_branch_sync import sync_branches


class BranchSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote = root / "remote.git"
        self.work = root / "work"
        self.peer = root / "peer"
        self.git(root, "init", "--bare", str(self.remote))
        self.git(root, "init", str(self.work))
        self.git(self.work, "config", "user.name", "CANO CI")
        self.git(self.work, "config", "user.email", "test@example.org")
        self.git(self.work, "checkout", "-b", "main")
        self.git(self.work, "remote", "add", "origin", str(self.remote))
        (self.work / "base.txt").write_text("baseline", encoding="utf-8")
        self.git(self.work, "add", ".")
        self.git(self.work, "commit", "-m", "baseline")
        self.git(self.work, "push", "-u", "origin", "main")
        self.git(self.work, "push", "origin", "main:prod")

    def git(self, cwd, *args):
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                                text=True, timeout=20)
        if result.returncode:
            self.fail("git fixture failed: " + " ".join(args) + "\n" + result.stderr[-500:])
        return result.stdout.strip()

    def commit(self, path, text):
        (self.work / path).write_text(text, encoding="utf-8")
        self.git(self.work, "add", path)
        self.git(self.work, "commit", "-m", path)
        self.git(self.work, "push", "origin", "main")

    def test_clean_fast_forward_is_idempotent(self):
        first = sync_branches(cwd=self.work, target="prod")
        self.assertEqual(first["status"], "already_in_sync")
        self.commit("new.txt", "new")
        moved = sync_branches(cwd=self.work, target="prod")
        self.assertEqual(moved["status"], "fast_forwarded")
        self.assertEqual(
            self.git(self.work, "ls-remote", "origin", "refs/heads/prod").split()[0],
            self.git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0],
        )
        again = sync_branches(cwd=self.work, target="prod")
        self.assertEqual(again["status"], "already_in_sync")

    def test_divergence_never_forces_or_loses_production_commit(self):
        self.commit("app.txt", "main-only")
        self.git(self.remote.parent, "clone", "-b", "prod", str(self.remote), str(self.peer))
        self.git(self.peer, "config", "user.name", "Other contributor")
        self.git(self.peer, "config", "user.email", "peer@example.org")
        (self.peer / "prod-only.txt").write_text("production work", encoding="utf-8")
        self.git(self.peer, "add", ".")
        self.git(self.peer, "commit", "-m", "production work")
        self.git(self.peer, "push", "origin", "prod")
        before = self.git(self.work, "ls-remote", "origin", "refs/heads/prod")
        with self.assertRaisesRegex(RuntimeError, "diverged"):
            sync_branches(cwd=self.work, target="prod")
        after = self.git(self.work, "ls-remote", "origin", "refs/heads/prod")
        self.assertEqual(before, after)

    def test_audit_reports_legacy_behind_without_pushing(self):
        self.commit("new.txt", "new")
        old = self.git(self.work, "ls-remote", "origin", "refs/heads/prod")
        result = sync_branches(cwd=self.work, target="prod", audit_only=True)
        self.assertEqual(result["status"], "legacy_behind_main")
        self.assertEqual(result["requires_human_review"], False)
        self.assertEqual(result["mutated"], False)
        self.assertEqual(old, self.git(self.work, "ls-remote", "origin", "refs/heads/prod"))

    def test_audit_reports_divergence_without_pushing_or_hiding_it(self):
        self.commit("main.txt", "main only")
        self.git(self.remote.parent, "clone", "-b", "prod", str(self.remote), str(self.peer))
        self.git(self.peer, "config", "user.name", "Other contributor")
        self.git(self.peer, "config", "user.email", "peer@example.org")
        (self.peer / "legacy-only.txt").write_text("preserve", encoding="utf-8")
        self.git(self.peer, "add", ".")
        self.git(self.peer, "commit", "-m", "legacy work")
        self.git(self.peer, "push", "origin", "prod")
        original = self.git(self.work, "ls-remote", "origin", "refs/heads/prod")
        result = sync_branches(cwd=self.work, target="prod", audit_only=True)
        self.assertEqual(result["status"], "legacy_diverged_requires_review")
        self.assertEqual(result["requires_human_review"], True)
        self.assertEqual(result["mutated"], False)
        self.assertEqual(original, self.git(self.work, "ls-remote", "origin", "refs/heads/prod"))

    def test_cli_requires_explicit_read_only_flag_and_preserves_remote(self):
        import json
        import sys

        # The CLI deliberately audits the named historical Render recovery ref.
        # This isolated fixture initially has only 'prod'; create that exact ref.
        legacy_ref = "refs/heads/fix/sqlite-backup-restore-20261031"
        self.git(self.work, "push", "origin",
                 "main:fix/sqlite-backup-restore-20261031")
        self.commit("new-for-cli.txt", "new")
        original = self.git(self.work, "ls-remote", "origin", legacy_ref)
        repo_root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PYTHONPATH=str(repo_root))
        command = [sys.executable, "-m", "scripts.cano_safe_branch_sync"]
        disallowed = subprocess.run(command, cwd=self.work, env=env,
                                    text=True, capture_output=True, timeout=30)
        self.assertNotEqual(disallowed.returncode, 0)
        allowed = subprocess.run(command + ["--audit-only"], cwd=self.work,
                                 env=env, text=True, capture_output=True, timeout=30)
        self.assertEqual(allowed.returncode, 0, allowed.stderr[-600:])
        receipt = json.loads(allowed.stdout.splitlines()[-1])
        self.assertEqual(receipt["status"], "legacy_behind_main")
        self.assertEqual(receipt["mutated"], False)
        self.assertEqual(original, self.git(self.work, "ls-remote", "origin", legacy_ref))

    def test_scheduled_workflow_can_only_audit_legacy_branch(self):
        repo = Path(__file__).resolve().parents[1]
        workflow = (repo / ".github/workflows/cano-safe-branch-sync.yml").read_text()
        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("python -m scripts.cano_safe_branch_sync --audit-only", workflow)

    def test_invalid_refs_rejected_without_git_access(self):
        for bad in ("../prod", "prod..evil", "-force", "main//evil", "prod.lock"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                sync_branches(cwd=self.work, target=bad)

    def test_daily_archive_has_single_canonical_main_target(self):
        repo = Path(__file__).resolve().parents[1]
        archive = (repo / ".github/workflows/daily-research-archive.yml").read_text()
        self.assertIn("ref: main", archive)
        self.assertIn("ARCHIVE_TARGET_BRANCH: main", archive)
        self.assertFalse((repo / ".github/workflows/scheduled-research-archive.yml").exists())


if __name__ == "__main__":
    unittest.main()
