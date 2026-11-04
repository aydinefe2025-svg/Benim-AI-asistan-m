import tempfile
import threading
import unittest
from pathlib import Path

from core.task_store import TaskStore


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tempdir.name) / "test.sqlite3")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_create_and_list(self):
        task = self.store.create("Kaynakları doğrula", "Önemli iddiaları kaynakla eşleştir")
        self.assertEqual(task["status"], "planned")
        self.assertEqual(len(self.store.list()), 1)

    def test_cannot_verify_without_evidence(self):
        task = self.store.create("Hesaplamayı çalıştır")
        with self.assertRaises(ValueError):
            self.store.transition(task["id"], "verified")

    def test_free_text_or_urls_cannot_verify_and_leave_no_audit_mutation(self):
        task = self.store.create("Testi çalıştır")
        self.store.transition(task["id"], "running")
        self.store.transition(task["id"], "done")
        before = self.store.get(task["id"]), self.store.history(task["id"])
        for evidence in (["unittest output: 3 tests passed"],
                         ["https://invalid.example/missing"],
                         ["https://arxiv.org/abs/1234.5678"] * 2,
                         ["Model says the scientific assertion is supported"]):
            with self.subTest(evidence=evidence), self.assertRaisesRegex(ValueError, "independent"):
                self.store.transition(task["id"], "verified", evidence=evidence)
            self.assertEqual((self.store.get(task["id"]), self.store.history(task["id"])), before)

    def test_illegal_transition_and_blank_verification_evidence_rejected(self):
        task = self.store.create("Geçişleri denetle")
        with self.assertRaises(ValueError):
            self.store.transition(task["id"], "verified", evidence=["  "])
        with self.assertRaises(ValueError):
            self.store.transition(task["id"], "done")
        self.assertEqual(self.store.get(task["id"])["status"], "planned")

    def test_review_pending_can_be_replanned_without_verification(self):
        task = self.store.create("Review a saved draft")
        self.store.transition(task["id"], "running")
        self.store.finish_draft(task["id"], "Unverified research notes")
        self.assertEqual(self.store.get(task["id"])["status"], "review_pending")
        with self.assertRaises(ValueError):
            self.store.transition(task["id"], "verified")
        self.assertEqual(self.store.transition(task["id"], "planned")["status"], "planned")
        self.assertEqual(self.store.history(task["id"])[-1]["new_status"], "planned")

    def test_failed_task_can_be_retried_but_verified_is_terminal(self):
        task = self.store.create("Hata kaydını denetle")
        self.store.transition(task["id"], "running")
        failed = self.store.transition(task["id"], "failed", note="provider error")
        self.assertEqual(failed["status"], "failed")
        self.store.transition(task["id"], "planned", note="manual retry")
        self.store.transition(task["id"], "running")
        self.store.transition(task["id"], "done")
        # Simulate an existing record from before the fail-closed gate.
        with self.store._connection() as conn:
            conn.execute("UPDATE tasks SET status='verified' WHERE id=?", (task["id"],))
        reopened = TaskStore(self.store.db_path)
        self.assertEqual(reopened.get(task["id"])["status"], "verified")
        with self.assertRaises(ValueError):
            self.store.transition(task["id"], "planned")

    def test_concurrent_conflicting_transitions_do_not_overwrite(self):
        task = self.store.create("Eşzamanlı güncelleme")
        barrier = threading.Barrier(2)
        outcomes = []

        def transition(status):
            barrier.wait()
            try:
                self.store.transition(task["id"], status)
                outcomes.append(status)
            except ValueError:
                outcomes.append("rejected")
            except Exception as exc:  # Surface unexpected SQLite/thread errors in the assertion.
                outcomes.append(f"unexpected:{type(exc).__name__}:{exc}")

        workers = [
            threading.Thread(target=transition, args=(status,))
            for status in ("running", "running")
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        final_status = self.store.get(task["id"])["status"]
        self.assertIn(final_status, {"running", "blocked"})
        self.assertEqual(final_status, "running")
        self.assertCountEqual(outcomes, ["rejected", "running"])
        self.assertEqual(len(self.store.history(task["id"])), 2)

    def test_old_schema_migrates_without_losing_tasks_or_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "old.sqlite3"
            # Build the previous schema exactly as it existed before failed was added.
            import sqlite3
            conn = sqlite3.connect(path)
            conn.executescript("""
                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, goal TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN ('planned','running','blocked','done','verified')),
                    evidence TEXT NOT NULL DEFAULT '[]', blockers TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(id), at TEXT NOT NULL,
                    old_status TEXT, new_status TEXT NOT NULL, note TEXT NOT NULL DEFAULT ''
                );
            """)
            conn.execute(
                "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)",
                ("legacy-task", "Keep me", "Old record", "planned", "[]", "[]", "2026-01-01", "2026-01-01"),
            )
            conn.execute(
                "INSERT INTO task_events(task_id,at,old_status,new_status,note) VALUES(?,?,?,?,?)",
                ("legacy-task", "2026-01-01", None, "planned", "Created before migration"),
            )
            conn.commit()
            conn.close()
            migrated = TaskStore(path)
            self.assertEqual(migrated.get("legacy-task")["title"], "Keep me")
            self.assertEqual(len(migrated.history("legacy-task")), 1)
            migrated.transition("legacy-task", "running")
            migrated.transition("legacy-task", "failed", note="migration verified")
            self.assertEqual(migrated.get("legacy-task")["status"], "failed")
            self.assertEqual(
                [event["new_status"] for event in migrated.history("legacy-task")],
                ["planned", "running", "failed"],
            )

    def test_unknown_status_rejected(self):
        task = self.store.create("Test")
        with self.assertRaises(ValueError):
            self.store.transition(task["id"], "magical")

    def test_empty_title_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create("  ")


if __name__ == "__main__":
    unittest.main()

