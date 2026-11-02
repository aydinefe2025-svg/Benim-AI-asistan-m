"""Regression tests for bounded research task execution."""
import tempfile
import unittest
from pathlib import Path
from core.task_store import TaskStore
from core.agent_executor import run_research_task


class ResearchExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.temp.name) / "tasks.sqlite3")
        self.task = self.store.create("Inspect evidence", "Find and assess sources")

    def tearDown(self):
        self.temp.cleanup()

    def test_success_is_done_but_not_verified(self):
        result = run_research_task(self.store, self.task["id"], lambda goal: "Draft: " + goal)
        self.assertEqual(result["status"], "done")
        self.assertFalse(result["verified"])
        self.assertEqual(self.store.get(self.task["id"])["status"], "done")
        self.assertEqual([event["new_status"] for event in self.store.history(self.task["id"])],
                         ["planned", "running", "done"])

    def test_provider_failure_is_blocked_and_retryable(self):
        def fail(_):
            raise RuntimeError("sensitive provider details")
        result = run_research_task(self.store, self.task["id"], fail)
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("sensitive", str(result))
        self.assertEqual(self.store.get(self.task["id"])["status"], "blocked")
        self.assertEqual(run_research_task(self.store, self.task["id"], lambda _: "Retry")["status"], "done")

    def test_empty_response_is_blocked(self):
        self.assertEqual(run_research_task(self.store, self.task["id"], lambda _: " ")["status"], "blocked")

    def test_completed_task_cannot_be_run_twice(self):
        run_research_task(self.store, self.task["id"], lambda _: "Draft")
        with self.assertRaises(ValueError):
            run_research_task(self.store, self.task["id"], lambda _: "Again")


if __name__ == "__main__":
    unittest.main()
