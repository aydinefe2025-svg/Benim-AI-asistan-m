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
            store.transition(task["id"], "running", note="Research started")
            store.transition(task["id"], "done", note="Research completed")
            # Seed a historical verified row; new verified transitions fail closed.
            with store._connection() as conn:
                conn.execute("UPDATE tasks SET status='verified', evidence=? WHERE id=?",
                             ('["old evidence"]', task["id"]))
            save_draft(store.db_path, task["id"], "Draft only")
            raw = export_research_archive(store)
            self.assertEqual(import_research_archive(store, raw), 1)
            tasks = store.list()
            self.assertEqual(len(tasks), 2)
            imported = next(item for item in tasks if item["id"] != task["id"])
            self.assertEqual(imported["status"], "planned")
            self.assertEqual(load_draft(store.db_path, imported["id"]), "Draft only")
            self.assertEqual(store.get(task["id"])["status"], "verified")

    def test_redeploy_recovery_preserves_audit_without_trusting_it(self):
        # Separate directories model an ephemeral server replacement. Only the
        # user-controlled downloaded JSON crosses into the new session.
        with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
            original = TaskStore(Path(old) / "old.sqlite3")
            task = original.create("Private study", "Check primary sources")
            original.transition(task["id"], "running", note="Original audit note")
            original.transition(task["id"], "done", evidence=["untrusted source note"])
            save_draft(original.db_path, task["id"], "Unverified draft")
            raw = export_research_archive(original)
            recovered = TaskStore(Path(new) / "new-session.sqlite3")
            existing = recovered.create("Keep existing data")
            self.assertEqual(import_research_archive(recovered, raw), 1)
            restored = next(t for t in recovered.list() if t["id"] != existing["id"])
            self.assertEqual(restored["status"], "planned")
            self.assertEqual(restored["evidence"], [])
            self.assertEqual(load_draft(recovered.db_path, restored["id"]), "Unverified draft")
            note = recovered.history(restored["id"])[0]["note"]
            archived = json.loads(note.split("Untrusted original record: ", 1)[1])
            self.assertEqual(archived, json.loads(raw)["tasks"][0])
            self.assertEqual(recovered.get(existing["id"])["title"], "Keep existing data")
            # Audit provenance also survives the next user-controlled export.
            self.assertIn("Original audit note", export_research_archive(recovered).decode())
            other_visitor = TaskStore(Path(new) / "other-session.sqlite3")
            self.assertEqual(other_visitor.list(), [])

    def test_truncated_backup_does_not_change_existing_session(self):
        with tempfile.TemporaryDirectory() as folder:
            store = TaskStore(Path(folder) / "tasks.sqlite3")
            task = store.create("Keep me")
            before = store.list(), store.history(task["id"])
            with self.assertRaises(ValueError):
                import_research_archive(store, export_research_archive(store)[:-4])
            self.assertEqual((store.list(), store.history(task["id"])), before)

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
