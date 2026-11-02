"""Agent V2 regression checks for the existing task ledger.

Run: python -m unittest discover -s tests -v
No external API, paid service, or credential is required.
"""
import tempfile
import unittest
from pathlib import Path

from core.task_store import TaskStore


class TaskStoreRegressionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "tasks.sqlite3"

    def test_reopen_preserves_task_and_history_on_same_disk(self):
        first = TaskStore(self.path)
        task = first.create("Review evidence", "Check two sources")
        first.transition(task["id"], "running", note="Started")
        reopened = TaskStore(self.path)
        self.assertEqual(reopened.get(task["id"])["status"], "running")
        self.assertEqual(
            [event["new_status"] for event in reopened.history(task["id"])],
            ["planned", "running"],
        )

    def test_blocked_task_retains_reason(self):
        store = TaskStore(self.path)
        task = store.create("Check research source")
        store.transition(task["id"], "blocked", blockers=["Source unavailable"])
        self.assertEqual(store.get(task["id"])["blockers"], ["Source unavailable"])
        self.assertEqual(len(store.list(status="blocked")), 1)

    def test_evidence_survives_subsequent_transitions(self):
        store = TaskStore(self.path)
        task = store.create("Audit")
        store.transition(task["id"], "done", evidence=["Report saved"])
        verified = store.transition(task["id"], "verified", evidence=["Reviewed report"])
        self.assertEqual(verified["evidence"], ["Report saved", "Reviewed report"])

    def test_invalid_filter_rejected(self):
        with self.assertRaises(ValueError):
            TaskStore(self.path).list(status="nonexistent")


if __name__ == "__main__":
    unittest.main()
