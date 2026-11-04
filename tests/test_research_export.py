"""Verify portable research archive includes tasks, history and drafts."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.task_store import TaskStore
from core.research_drafts import save_draft
from core.research_export import export_research_archive


class ResearchExportTests(unittest.TestCase):
    def test_export_contains_task_history_and_draft(self):
        with tempfile.TemporaryDirectory() as folder:
            store = TaskStore(Path(folder) / "tasks.sqlite3")
            task = store.create("Study source", "Assess evidence")
            store.transition(task["id"], "running", note="Research started")
            store.transition(task["id"], "done", note="Draft prepared")
            save_draft(store.db_path, task["id"], "Not independently verified")
            data = json.loads(export_research_archive(store))
            self.assertEqual(data["schema"], "research-task-export-v1")
            self.assertEqual(len(data["tasks"]), 1)
            self.assertEqual(data["tasks"][0]["draft"], "Not independently verified")
            self.assertEqual(len(data["tasks"][0]["history"]), 3)
            self.assertEqual(data["tasks"][0]["status"], "done")

    def test_export_rejects_too_many_tasks(self):
        with tempfile.TemporaryDirectory() as folder:
            store = TaskStore(Path(folder) / "tasks.sqlite3")
            with patch.object(store, "list", return_value=[{}] * 201):
                with self.assertRaises(ValueError):
                    export_research_archive(store)


if __name__ == "__main__":
    unittest.main()
