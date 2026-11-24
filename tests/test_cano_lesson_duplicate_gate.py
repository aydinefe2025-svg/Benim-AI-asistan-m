import tempfile
import unittest
from pathlib import Path
from core.agent_colony import AgentColony

class LessonDuplicateGateTests(unittest.TestCase):
    def test_real_duplicate_pair_stays_pending_after_approval_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            colony = AgentColony(Path(folder) / "colony.sqlite3")
            agent = colony.create_founder("research", "Check evidence")
            task = "CANO için ölçülebilir gelişim önerisi hazırla"
            first = "**Her öneri, “İşlem – Beklenen Çıktı – Doğrulama Ölçütü” üçlülerini tablo içinde sunmalı; böylece denetim adımları otomatik raporlamaya hazır hâle gelir.**"
            second = "**Her öneri, “İşlem – Beklenen Çıktı – Doğrulama Ölçütü” üçlüsüyle sunulmalı; böylece denetim adımları otomatik raporlamaya hazır hâle gelir.**"
            colony.feedback(agent, task, first, "mission_review:first", accepted=True)
            pending = colony.feedback(agent, task, second, "mission_review:second")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                colony.approve_feedback(pending, approved=True)
            self.assertEqual(colony.evaluate_learning(agent)["accepted_lessons"], 1)
            self.assertEqual(len(colony.lessons(agent, task=task)), 1)
            with colony._db() as db:
                self.assertEqual(db.execute("SELECT accepted FROM colony_feedback WHERE id=?", (pending,)).fetchone()[0], 0)

    def test_distinct_lesson_can_be_approved_and_other_agent_is_not_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            colony = AgentColony(Path(folder) / "colony.sqlite3")
            agent = colony.create_founder("research", "Check evidence")
            child = colony.spawn(agent, "reviewer", "Review evidence", approved=True)
            task = "test quality"
            colony.feedback(agent, task, "Check primary evidence before claiming a result.", "note", accepted=True)
            distinct = colony.feedback(agent, task, "Run tests and preserve failed results.", "note2")
            self.assertEqual(colony.approve_feedback(distinct, approved=True)["status"], "accepted")
            sibling_scope = colony.feedback(child, task, "Check primary evidence before claiming a result.", "note3")
            self.assertEqual(colony.approve_feedback(sibling_scope, approved=True)["status"], "accepted")
