import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony


class FakeClient:
    def __init__(self):
        self.prompts = []

    def chat(self, model, system, prompt):
        self.prompts.append(prompt)
        return "Evidence-labelled draft"


class ColonyTests(unittest.TestCase):
    def test_spawn_persistence_quota_and_generation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "colony.sqlite3"
            colony = AgentColony(path, max_agents=2)
            founder = colony.create_founder("research", "Research carefully")
            with self.assertRaises(PermissionError):
                colony.spawn(founder, "review", "Check claims")
            child = colony.spawn(founder, "review", "Check claims", approved=True)
            reopened = AgentColony(path, max_agents=2)
            self.assertEqual(reopened.get(child)["parent_id"], founder)
            self.assertEqual(reopened.get(child)["generation"], 1)
            with self.assertRaises(RuntimeError):
                reopened.spawn(founder, "extra", "Extra", approved=True)

    def test_accepted_feedback_changes_future_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "colony.sqlite3"
            colony = AgentColony(path)
            founder = colony.create_founder("research", "Research carefully")
            client = FakeClient()
            first = colony.run(founder, "Question", client=client, model="mock")
            self.assertEqual(first["lessons_used"], 0)
            colony.feedback(founder, "Question", "Unreviewed guess", "note", accepted=False)
            colony.feedback(founder, "Question", "Check primary evidence", "review-id-1", accepted=True)
            reopened = AgentColony(path)
            second = reopened.run(founder, "Question", client=client, model="mock")
            self.assertEqual(second["lessons_used"], 1)
            self.assertIn("Check primary evidence", client.prompts[-1])
            self.assertNotIn("Unreviewed guess", client.prompts[-1])
            self.assertEqual(second["status"], "draft_unverified")

    def test_founder_unique_and_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            colony = AgentColony(Path(folder) / "colony.sqlite3")
            founder = colony.create_founder("research", "Careful")
            with self.assertRaises(RuntimeError):
                colony.create_founder("second", "No")
            with self.assertRaises(ValueError):
                colony.feedback(founder, "", "lesson", "evidence", accepted=True)


if __name__ == "__main__":
    unittest.main()
