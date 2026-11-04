import tempfile
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

    def test_verified_task_keeps_evidence_and_history(self):
        task = self.store.create("Testi çalıştır")
        updated = self.store.transition(
            task["id"], "verified", note="Unit tests passed",
            evidence=["unittest output: 3 tests passed"],
        )
        self.assertEqual(updated["status"], "verified")
        self.assertIn("unittest output: 3 tests passed", updated["evidence"])
        history = self.store.history(task["id"])
        self.assertEqual([event["new_status"] for event in history], ["planned", "verified"])

    def test_unknown_status_rejected(self):
        task = self.store.create("Test")
        with self.assertRaises(ValueError):
            self.store.transition(task["id"], "magical")

    def test_empty_title_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create("  ")


if __name__ == "__main__":
    unittest.main()
