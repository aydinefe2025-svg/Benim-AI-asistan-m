import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.task_store import TaskStore
from core.task_heartbeat_runner import running_heartbeat


class HeartbeatFailureTests(unittest.TestCase):
    def test_heartbeat_storage_failure_is_not_silent(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "tasks.sqlite3"
            store = TaskStore(db)
            task = store.create("Heartbeat failure")
            store.transition(task["id"], "running")
            calls = [0]

            def failing_touch(*args, **kwargs):
                calls[0] += 1
                if calls[0] > 1:
                    raise OSError("database unavailable")
                return True

            with patch("core.task_heartbeat_runner.touch_running", side_effect=failing_touch):
                with self.assertRaisesRegex(RuntimeError, "heartbeat failed"):
                    with running_heartbeat(db, task["id"], interval_seconds=0.005):
                        time.sleep(0.04)

    def test_lost_running_status_is_not_silent(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "tasks.sqlite3"
            store = TaskStore(db)
            task = store.create("Lost ownership")
            store.transition(task["id"], "running")
            with self.assertRaisesRegex(RuntimeError, "lost heartbeat ownership"):
                with running_heartbeat(db, task["id"], interval_seconds=0.005):
                    store.transition(task["id"], "blocked", note="External cancellation")
                    time.sleep(0.04)


if __name__ == "__main__":
    unittest.main()
