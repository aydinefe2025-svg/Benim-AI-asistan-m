"""Regression: keep owner-scoped SQLite tasks private on main and production.

Tests run only on temporary local files. No external provider or live data.
"""
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

from core.authorized_queue import AuthorizedQueue


@unittest.skipUnless(os.name == "posix", "POSIX owner-file privacy contract")
class AuthorizedQueuePrivateFileTests(unittest.TestCase):
    def test_reopen_existing_queue_and_rollback_journal_are_owner_private(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "owner-queue.sqlite3"
            queue = AuthorizedQueue(path, owner_key="synthetic-owner", max_jobs=3)
            job = queue.enqueue("private-1", "Sensitive synthetic goal", approved=True)
            os.chmod(path, 0o644)  # Simulates an old insecure database.
            reopened = AuthorizedQueue(path, owner_key="synthetic-owner", max_jobs=3)
            self.assertEqual(reopened.get(job["id"])["state"], "queued")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE authorized_jobs SET goal=? WHERE id=?",
                    ("Synthetic private text", job["id"]),
                )
                journal = Path(str(path) + "-journal")
                self.assertTrue(journal.is_file())
                self.assertEqual(stat.S_IMODE(journal.stat().st_mode), 0o600)

    def test_symlink_target_is_rejected_before_creating_a_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "unrelated.sqlite3"
            link = root / "linked-queue.sqlite3"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                AuthorizedQueue(link, owner_key="synthetic-owner", max_jobs=3)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
