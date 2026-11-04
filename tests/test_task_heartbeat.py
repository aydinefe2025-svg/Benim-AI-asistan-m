import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.task_store import TaskStore
from core.task_heartbeat import touch_running
from core.task_recovery import recover_stale_running


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "tasks.sqlite3"
        self.store = TaskStore(self.db)
        self.task = self.store.create("Heartbeat test")
        self.now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_running_task_can_heartbeat(self):
        self.assertFalse(touch_running(self.db, self.task["id"], now=self.now))
        self.store.transition(self.task["id"], "running")
        self.assertTrue(touch_running(self.db, self.task["id"], now=self.now))

    def test_heartbeat_prevents_stale_recovery(self):
        self.store.transition(self.task["id"], "running")
        touch_running(self.db, self.task["id"], now=self.now)
        recovered = recover_stale_running(self.db, now=self.now + timedelta(minutes=30))
        self.assertEqual(recovered, [])
        self.assertEqual(self.store.get(self.task["id"])["status"], "running")

    def test_stale_heartbeat_allows_recovery(self):
        self.store.transition(self.task["id"], "running")
        touch_running(self.db, self.task["id"], now=self.now - timedelta(hours=2))
        recovered = recover_stale_running(self.db, now=self.now)
        self.assertEqual(recovered, [self.task["id"]])
        self.assertFalse(touch_running(self.db, self.task["id"], now=self.now))

    def test_naive_timestamp_rejected(self):
        self.store.transition(self.task["id"], "running")
        with self.assertRaises(ValueError):
            touch_running(self.db, self.task["id"], now=datetime(2026, 11, 3))


if __name__ == "__main__":
    unittest.main()
