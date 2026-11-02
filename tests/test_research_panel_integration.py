"""User-triggered research panel integration regression tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.task_panel import render_task_panel
from core.task_store import TaskStore
from core.research_drafts import load_draft
from tests.test_task_panel import FakeStreamlit


class ClickResearchStreamlit(FakeStreamlit):
    def button(self, label, **kwargs):
        return kwargs.get("key", "").startswith("run_")


class ResearchPanelIntegrationTests(unittest.TestCase):
    def test_user_click_generates_persistent_unverified_draft(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "tasks.sqlite3")
            task = TaskStore(path).create("Study", "Find sources")
            st = ClickResearchStreamlit(submits=[False, False])
            with patch.dict("os.environ", {"AGENT_TASK_DB_PATH": path}):
                render_task_panel(st, answer=lambda goal: "Unverified: " + goal)
            self.assertEqual(TaskStore(path).get(task["id"])["status"], "done")
            self.assertEqual(load_draft(path, task["id"]), "Unverified: Find sources")

    def test_without_provider_does_not_run(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "tasks.sqlite3")
            task = TaskStore(path).create("Study", "Find sources")
            st = ClickResearchStreamlit(submits=[False, False])
            with patch.dict("os.environ", {"AGENT_TASK_DB_PATH": path}):
                render_task_panel(st)
            self.assertEqual(TaskStore(path).get(task["id"])["status"], "planned")


if __name__ == "__main__":
    unittest.main()
