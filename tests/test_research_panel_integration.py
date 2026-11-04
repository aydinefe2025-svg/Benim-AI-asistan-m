"""User-triggered research panel integration regression tests."""
import tempfile
from datetime import datetime, timezone, timedelta
import sqlite3
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch

from core.task_panel import render_task_panel, _session_database_path
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
            st = ClickResearchStreamlit(submits=[False, False])
            db_path = _session_database_path(st, path)
            task = TaskStore(db_path).create("Study", "Find sources")
            with patch.dict("os.environ", {"AGENT_TASK_DB_PATH": path}):
                render_task_panel(st, answer=lambda goal: "Unverified: " + goal)
            self.assertEqual(TaskStore(db_path).get(task["id"])["status"], "review_pending")
            self.assertEqual(load_draft(db_path, task["id"]), "Unverified: Find sources")

    def test_panel_recovers_stale_running_without_provider_call(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "tasks.sqlite3")
            st = FakeStreamlit(submits=[False, False])
            db_path = _session_database_path(st, path)
            store = TaskStore(db_path)
            task = store.create("Interrupted", "Find evidence")
            store.transition(task["id"], "running", note="Started")
            stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("UPDATE tasks SET updated_at=? WHERE id=?", (stale, task["id"]))
            calls = []
            with patch.dict("os.environ", {"AGENT_TASK_DB_PATH": path}):
                render_task_panel(st, answer=lambda goal: calls.append(goal))
            self.assertEqual(TaskStore(db_path).get(task["id"])["status"], "blocked")
            self.assertEqual(calls, [])

    def test_without_provider_does_not_run(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "tasks.sqlite3")
            st = ClickResearchStreamlit(submits=[False, False])
            db_path = _session_database_path(st, path)
            task = TaskStore(db_path).create("Study", "Find sources")
            with patch.dict("os.environ", {"AGENT_TASK_DB_PATH": path}):
                render_task_panel(st)
            self.assertEqual(TaskStore(db_path).get(task["id"])["status"], "planned")


if __name__ == "__main__":
    unittest.main()
