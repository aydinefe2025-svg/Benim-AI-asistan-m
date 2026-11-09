import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony
from core.agent_review_loop import AgentReviewLoop


class FakeClient:
    def __init__(self):
        self.prompts = []

    def chat(self, model, system, prompt):
        self.prompts.append((system, prompt))
        return "draft " + str(len(self.prompts))


class ReviewLoopTests(unittest.TestCase):
    def test_three_pass_review_and_persistent_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "colony.sqlite3"
            colony = AgentColony(path)
            author = colony.create_founder("researcher", "Research carefully")
            reviewer = colony.spawn(author, "skeptic", "Check evidence", approved=True)
            colony.feedback(author, "*", "Check primary sources", "reviewed:test",
                            accepted=True)
            client = FakeClient()
            loop = AgentReviewLoop(colony)
            result = loop.execute(author, reviewer, "Research the mechanism",
                                  client=client, model="test-model")
            self.assertEqual(len(client.prompts), 3)
            self.assertIn("Check primary sources", client.prompts[0][1])
            self.assertIn("draft 1", client.prompts[1][1])
            self.assertIn("draft 2", client.prompts[2][1])
            self.assertEqual(result["status"], "review_pending")
            self.assertEqual(AgentReviewLoop(AgentColony(path)).get(result["id"]), result)

    def test_no_self_review_and_no_partial_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "colony.sqlite3")
            author = colony.create_founder("researcher", "Research")
            loop = AgentReviewLoop(colony)
            with self.assertRaises(ValueError):
                loop.execute(author, author, "Task", client=FakeClient(), model="test")
            with colony._db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM colony_reviews").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()

