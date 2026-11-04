"""Regression: leaving a heartbeat context must not leak SQLite worker threads."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from core.task_store import TaskStore
from core.task_heartbeat_runner import running_heartbeat


class HeartbeatThreadShutdownTests(unittest.TestCase):
    def test_exit_waits_for_inflight_heartbeat_before_sqlite_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.sqlite3"
            store = TaskStore(db_path)
            task = store.create("safe synthetic heartbeat", "verify teardown")
            store.transition(task["id"], "running")
            started, release = threading.Event(), threading.Event()
            calls = [0]

            def touch(db, task_id):
                calls[0] += 1
                if calls[0] == 1:  # synchronous, before thread starts
                    return True
                started.set()
                release.wait(timeout=0.12)  # simulate a bounded in-flight SQLite operation
                return True

            try:
                with patch("core.task_heartbeat_runner.touch_running", side_effect=touch):
                    with running_heartbeat(db_path, task["id"], interval_seconds=0.005):
                        self.assertTrue(started.wait(timeout=1), "heartbeat never began")
                    self.assertFalse(
                        any(t.name == "research-task-heartbeat" and t.is_alive()
                            for t in threading.enumerate()),
                        "heartbeat context returned while SQLite worker was active",
                    )
            finally:
                release.set()  # prevent a leaking thread even in a failing regression