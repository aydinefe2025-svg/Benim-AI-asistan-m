"""Portable research archive import safety tests."""
import json
import tempfile
import unittest
from pathlib import Path

from core.task_store import TaskStore
from core.research_drafts import save_draft, load_draft
from core.research_export import export_research_archive
from core.research_import import import_research_archive


class ResearchImportTests(unittest.TestCase):
    def test_round_trip_preserves_original_and_restarts_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            store = TaskStore(Path(folder) / "tasks.sqlite3")
            task = store.create("Study", "Check evidence")
            store.transition(task["id"], "running")
            store.transition(task["id"], "done")
            store.transition(task["id"], "verified", evidence=["old evidence"])
            save_draft(store.db_path, task["id"], "Draft only")
            raw = export_research_archive(store)
            self.assertEqual(import_research_archive(store, raw), 1)
            tasks = store.list()
            self.assertEqual(len(tasks), 2)
            imported = next(item for item in tasks if item["id"] != task["id"])
            self.assertEqual(imported["status"], "planned")
            self.assertEqual(load_draft(store.db_path, imported["id"]), "Draft only")
            self.assertEqual(store.get(task["id"])["status"], "verified")

    def test_invalid_entry_is_atomic(self):
        with tempfile.TemporaryDirectory() as folder:
            store = TaskStore(Path(folder) / "tasks.sqlite3")
            payload = {"schema": "research-task-export-v1", "tasks": [
                {"title": "Valid", "goal": "", "draft": None},
                {"title": "", "goal": "", "draft": None},
            ]}
            with self.assertRaises(ValueError):
                import_research_archive(store, json.dumps(payload).encode())
            self.assertEqual(store.list(), [])

    def test_rejects_wrong_schema_and_oversized_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            store = TaskStore(Path(folder) / "tasks.sqlite3")
            with self.assertRaises(ValueError):
                import_research_archive(store, b'{"schema":"unknown","tasks":[]}')
            with self.assertRaises(ValueError):
                import_research_archive(store, b"x" * 3_000_001)


if __name__ == "__main__":
    unittest.main()
