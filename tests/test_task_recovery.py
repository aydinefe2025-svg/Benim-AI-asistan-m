import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.task_store import TaskStore
from core.task_recovery import recover_stale_running


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "tasks.sqlite3"
        self.store = TaskStore(self.db)
        self.task = self.store.create("Interrupted research", "Test recovery")
        self.store.transition(self.task["id"], "running", note="Started")
        self.now = datetime(2026, 11, 3, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def set_updated(self, stamp):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE tasks SET updated_at=? WHERE id=?",
                         (stamp.isoformat(), self.task["id"]))

    def test_old_running_is_blocked_once(self):
        self.set_updated(self.now - timedelta(hours=2))
        self.assertEqual(recover_stale_running(self.db, now=self.now), [self.task["id"]])
        self.assertEqual(self.store.get(self.task["id"])["status"], "blocked")
        self.assertEqual(recover_stale_running(self.db, now=self.now), [])
        self.assertEqual([x["new_status"] for x in self.store.history(self.task["id"])].count("blocked"), 1)

    def test_recent_running_is_not_recovered(self):
        self.set_updated(self.now - timedelta(minutes=10))
        self.assertEqual(recover_stale_running(self.db, now=self.now), [])
        self.assertEqual(self.store.get(self.task["id"])["status"], "running")

    def test_no_automatic_provider_execution(self):
        self.set_updated(self.now - timedelta(hours=2))
        recover_stale_running(self.db, now=self.now)
        self.assertIn("review before retry", self.store.get(self.task["id"])["blockers"][0])

    def test_invalid_timeout_rejected(self):
        with self.assertRaises(ValueError):
            recover_stale_running(self.db, stale_after_seconds=0, now=self.now)


if __name__ == "__main__":
    unittest.main()
