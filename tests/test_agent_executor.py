"""Regression tests for bounded research task execution."""
import tempfile
import unittest
from pathlib import Path
from core.task_store import TaskStore
from core.agent_executor import run_research_task
from core.research_drafts import load_draft


class ResearchExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.temp.name) / "tasks.sqlite3")
        self.task = self.store.create("Inspect evidence", "Find and assess sources")

    def tearDown(self):
        self.temp.cleanup()

    def test_success_is_review_pending_but_not_verified(self):
        result = run_research_task(self.store, self.task["id"], lambda goal: "Draft: " + goal)
        self.assertEqual(result["status"], "review_pending")
        self.assertFalse(result["verified"])
        self.assertEqual(self.store.get(self.task["id"])["status"], "review_pending")
        self.assertEqual([event["new_status"] for event in self.store.history(self.task["id"])],
                         ["planned", "running", "review_pending"])

    def test_provider_failure_is_blocked_and_retryable(self):
        def fail(_):
            raise RuntimeError("sensitive provider details")
        result = run_research_task(self.store, self.task["id"], fail)
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("sensitive", str(result))
        self.assertEqual(self.store.get(self.task["id"])["status"], "blocked")
        self.assertEqual(run_research_task(self.store, self.task["id"], lambda _: "Retry")["status"], "review_pending")

    def test_empty_response_is_blocked(self):
        self.assertEqual(run_research_task(self.store, self.task["id"], lambda _: " ")["status"], "blocked")

    def test_completed_task_cannot_be_run_twice(self):
        run_research_task(self.store, self.task["id"], lambda _: "Draft")
        with self.assertRaises(ValueError):
            run_research_task(self.store, self.task["id"], lambda _: "Again")

    def test_transient_outage_has_bounded_exponential_retry(self):
        calls, delays = [], []
        def transient(_):
            calls.append(1)
            if len(calls) < 3:
                raise TimeoutError("secret provider details")
            return "Recovered draft"
        result = run_research_task(self.store, self.task["id"], transient, sleep=delays.append)
        self.assertEqual(result["status"], "review_pending")
        self.assertEqual(delays, [1, 2])
        self.assertEqual(load_draft(self.store.db_path, self.task["id"]), "Recovered draft")

    def test_draft_write_failure_does_not_mark_task_complete(self):
        with self.store._connection() as conn:
            conn.execute("""CREATE TRIGGER reject_draft_event BEFORE INSERT ON task_events
                WHEN NEW.new_status='review_pending' BEGIN SELECT RAISE(ABORT,'simulated crash'); END""")
        result = run_research_task(self.store, self.task["id"], lambda _: "Unsaved draft")
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(load_draft(self.store.db_path, self.task["id"]))
        self.assertNotIn("review_pending", [x["new_status"] for x in self.store.history(self.task["id"])])

    def test_external_block_during_provider_is_preserved(self):
        task_id = self.task["id"]
        def cancelled(_):
            self.store.transition(task_id, "blocked", note="Cancelled by operator")
            return "Draft should not be stored"
        result = run_research_task(self.store, task_id, cancelled)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.store.get(task_id)["status"], "blocked")
        self.assertIsNone(load_draft(self.store.db_path, task_id))

    def test_heartbeat_failure_cannot_save_provider_draft(self):
        from contextlib import contextmanager
        from unittest.mock import patch

        @contextmanager
        def heartbeat_failure(*_args, **_kwargs):
            yield
            raise RuntimeError("Heartbeat failed")

        with patch("core.agent_executor.running_heartbeat", heartbeat_failure):
            result = run_research_task(self.store, self.task["id"], lambda _: "Unsaved draft")
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(load_draft(self.store.db_path, self.task["id"]))

    def test_interrupted_task_can_be_explicitly_recovered(self):
        def interrupt(_):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            run_research_task(self.store, self.task["id"], interrupt)
        self.assertEqual(self.store.get(self.task["id"])["status"], "running")
        self.assertIsNone(load_draft(self.store.db_path, self.task["id"]))
        self.store.transition(self.task["id"], "blocked", note="User recovered interrupted run")
        self.assertEqual(run_research_task(self.store, self.task["id"], lambda _: "Recovered")["status"],
                         "review_pending")


if __name__ == "__main__":
    unittest.main()
