"""Research drafts are durable across UI sessions on the same SQLite disk."""
import tempfile
import unittest
from pathlib import Path

from core.task_store import TaskStore
from core.research_drafts import load_draft, save_draft


class DraftStoreTests(unittest.TestCase):
    def test_save_read_update_and_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "tasks.sqlite3"
            task = TaskStore(db).create("Test research")
            self.assertIsNone(load_draft(str(db), task["id"]))
            save_draft(str(db), task["id"], "First result")
            self.assertEqual(load_draft(str(db), task["id"]), "First result")
            save_draft(str(db), task["id"], "Revised result")
            self.assertEqual(load_draft(str(db), task["id"]), "Revised result")
            self.assertIsNone(load_draft(str(db), "not-a-task"))

    def test_reject_empty_and_unknown_task(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "tasks.sqlite3"
            TaskStore(db)
            with self.assertRaises(ValueError):
                save_draft(str(db), "missing", "")
            with self.assertRaises(Exception):
                save_draft(str(db), "missing", "Not an existing task")


if __name__ == "__main__":
    unittest.main()
