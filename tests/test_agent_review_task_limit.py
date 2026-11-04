import tempfile
import unittest
from pathlib import Path
from core.agent_colony import AgentColony
from core.agent_review_loop import AgentReviewLoop


class FakeModel:
    def __init__(self):
        self.calls = 0
    def chat(self, model, system, prompt):
        self.calls += 1
        return ("Draft: " + "evidence " * 450) if self.calls == 1 else (
            "Critique: " + "check " * 450 if self.calls == 2 else "Revised response")


class ReviewTaskLimitTests(unittest.TestCase):
    def test_long_generated_draft_can_be_reviewed(self):
        with tempfile.TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "colony.db")
            author = colony.create_founder("writer", "Write carefully")
            reviewer = colony.spawn(author, "reviewer", "Review carefully", approved=True)
            model = FakeModel()
            result = AgentReviewLoop(colony).execute(
                author, reviewer, "Check a simple fact", client=model, model="fake")
            self.assertEqual(model.calls, 3)
            self.assertEqual(result["status"], "review_pending")
            self.assertIn("Critique:", result["critique"])

    def test_user_task_limit_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "colony.db")
            author = colony.create_founder("writer", "Write carefully")
            with self.assertRaises(ValueError):
                colony.run(author, "a" * 3001, client=FakeModel(), model="fake")


if __name__ == "__main__":
    unittest.main()
