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
            colony.feedback(founder, "*", "Check primary evidence", "review-id-1", accepted=True)
            reopened = AgentColony(path)
            second = reopened.run(founder, "Question", client=client, model="mock")
            self.assertEqual(second["lessons_used"], 1)
            self.assertIn("Check primary evidence", client.prompts[-1])
            self.assertNotIn("Unreviewed guess", client.prompts[-1])
            self.assertIn("Task: Question\nAccepted past lessons", client.prompts[-1])
            self.assertIn("Separate facts, hypotheses and missing evidence.",
                          client.prompts[-1])
            self.assertNotIn(r"\nAccepted past lessons", client.prompts[-1])
            self.assertEqual(second["status"], "draft_unverified")

    def test_task_matching_uses_relevant_and_global_lessons_only(self):
        with tempfile.TemporaryDirectory() as folder:
            colony = AgentColony(Path(folder) / "colony.sqlite3")
            founder = colony.create_founder("research", "Research carefully")
            colony.feedback(founder, "release deployment",
                            "Require human approval before deployment",
                            "review:deployment", accepted=True)
            colony.feedback(founder, "primary source DOI evidence",
                            "Check DOI and verify the primary source evidence",
                            "review:source", accepted=True)
            colony.feedback(founder, "*", "Separate facts from hypotheses",
                            "review:global", accepted=True)
            colony.feedback(founder, "primary source evidence",
                            "Never check evidence", "review:unreviewed", accepted=False)
            client = FakeClient()

            result = colony.run(
                founder, "Verify DOI citation evidence from the primary source",
                client=client, model="mock")
            self.assertEqual(result["lessons_used"], 2)
            self.assertIn("Check DOI and verify the primary source evidence",
                          client.prompts[-1])
            self.assertIn("Separate facts from hypotheses", client.prompts[-1])
            self.assertNotIn("Require human approval", client.prompts[-1])
            self.assertNotIn("Never check evidence", client.prompts[-1])

            unrelated = colony.run(
                founder, "Explain a quantum graph",
                client=client, model="mock")
            self.assertEqual(unrelated["lessons_used"], 1)
            self.assertIn("Separate facts from hypotheses", client.prompts[-1])
            self.assertNotIn("Check DOI and verify", client.prompts[-1])

    def test_task_matching_requires_nonempty_query(self):
        with tempfile.TemporaryDirectory() as folder:
            colony = AgentColony(Path(folder) / "colony.sqlite3")
            founder = colony.create_founder("research", "Research carefully")
            with self.assertRaises(ValueError):
                colony.lessons(founder, task=" ")

    def test_rejects_oversized_task_without_model_call(self):
        with tempfile.TemporaryDirectory() as folder:
            colony = AgentColony(Path(folder) / "colony.sqlite3")
            founder = colony.create_founder("research", "Careful")
            client = FakeClient()
            with self.assertRaises(ValueError):
                colony.run(founder, "x" * 3001, client=client, model="mock")
            self.assertEqual(client.prompts, [])

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


