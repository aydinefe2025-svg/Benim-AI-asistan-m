import tempfile
import unittest
from pathlib import Path

from core.task_store import TaskStore
from core.evidence_gate import record_evidence_review


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "tasks.db"
        self.store = TaskStore(self.db)
        self.task = self.store.create("Evidence review", "Find original sources")
        self.store.transition(self.task["id"], "running", note="Test")
        self.store.finish_draft(self.task["id"], "Unverified draft")

    def tearDown(self):
        self.tmp.cleanup()

    def review(self, **overrides):
        args = dict(source_url="https://example.org/primary",
                    evidence_note="Checked source supports the precise claim",
                    reviewer="independent-reviewer", accepted=True)
        args.update(overrides)
        return record_evidence_review(self.db, self.task["id"], **args)

    def test_accepted_review_verifies_and_preserves_event(self):
        result = self.review()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.store.get(self.task["id"])["status"], "verified")
        self.assertEqual(self.store.history(self.task["id"])[-1]["new_status"], "verified")

    def test_rejected_review_stays_pending(self):
        self.assertEqual(self.review(accepted=False)["status"], "review_pending")
        self.assertEqual(self.store.get(self.task["id"])["status"], "review_pending")

    def test_missing_evidence_cannot_verify(self):
        with self.assertRaises(ValueError):
            self.review(evidence_note="")
        self.assertEqual(self.store.get(self.task["id"])["status"], "review_pending")

    def test_second_review_cannot_reverify(self):
        self.review()
        with self.assertRaises(ValueError):
            self.review()

    def test_event_failure_rolls_back_review_and_status(self):
        with self.store._connection() as conn:
            conn.execute("""CREATE TRIGGER reject_review BEFORE INSERT ON task_events
                WHEN NEW.new_status='verified'
                BEGIN SELECT RAISE(ABORT,'simulated crash'); END""")
        with self.assertRaises(Exception):
            self.review()
        self.assertEqual(self.store.get(self.task["id"])["status"], "review_pending")
        with self.store._connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM evidence_reviews").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
