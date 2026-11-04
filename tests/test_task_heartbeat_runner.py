import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.task_store import TaskStore
from core.agent_executor import run_research_task
from core.task_heartbeat_runner import running_heartbeat


class HeartbeatRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "tasks.sqlite3"
        self.store = TaskStore(self.db)
        self.task = self.store.create("Long provider", "Check sources")

    def tearDown(self):
        self.tmp.cleanup()

    def test_requires_running_task(self):
        with self.assertRaises(ValueError):
            with running_heartbeat(self.db, self.task["id"], interval_seconds=0.01):
                pass

    def test_runner_is_used_during_provider_call(self):
        calls = []
        from contextlib import contextmanager

        @contextmanager
        def spy(db_path, task_id):
            calls.append(("start", task_id))
            yield
            calls.append(("stop", task_id))

        with patch("core.agent_executor.running_heartbeat", spy):
            result = run_research_task(self.store, self.task["id"], lambda goal: "Draft")
        self.assertEqual(result["status"], "review_pending")
        self.assertEqual(calls, [("start", self.task["id"]), ("stop", self.task["id"])])

    def test_background_storage_failure_blocks_provider_draft(self):
        self.store.transition(self.task["id"], "running")
        calls = [0]
        original = self.store.touch_running

        def fails_after_start(task_id):
            calls[0] += 1
            if calls[0] > 1:
                raise OSError("storage temporarily unavailable")
            return original(task_id)

        with patch.object(self.store, "touch_running", side_effect=fails_after_start):
            with self.assertRaisesRegex(RuntimeError, "heartbeat"):
                with running_heartbeat(self.store, self.task["id"],
                                       interval_seconds=0.005):
                    time.sleep(0.04)

    def test_lost_running_ownership_is_detected(self):
        self.store.transition(self.task["id"], "running")
        with self.assertRaisesRegex(RuntimeError, "heartbeat ownership"):
            with running_heartbeat(self.store, self.task["id"],
                                   interval_seconds=0.005):
                self.store.transition(self.task["id"], "blocked",
                                      note="External cancellation")
                time.sleep(0.04)

    def test_legitimate_review_transition_is_not_a_failure(self):
        self.store.transition(self.task["id"], "running")
        with running_heartbeat(self.store, self.task["id"],
                               interval_seconds=0.005):
            self.store.finish_draft(self.task["id"], "Approved draft")
            time.sleep(0.04)
        self.assertEqual(self.store.get(self.task["id"])["status"],
                         "review_pending")

    def test_heartbeat_does_not_change_terminal_status(self):
        self.store.transition(self.task["id"], "running")
        with running_heartbeat(self.db, self.task["id"], interval_seconds=0.01):
            self.store.finish_draft(self.task["id"], "Draft")
        self.assertEqual(self.store.get(self.task["id"])["status"], "review_pending")


if __name__ == "__main__":
    unittest.main()
