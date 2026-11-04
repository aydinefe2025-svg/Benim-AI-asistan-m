import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission


class FakeClient:
    def __init__(self):
        self.calls = []

    def chat(self, model, system, prompt):
        self.calls.append((model, system, prompt))
        return "Result " + str(len(self.calls))


class CollaborativeMissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.colony = AgentColony(Path(self.tmp.name) / "colony.sqlite3")
        self.colony.create_founder("research", "Research carefully")
        self.colony.grow_specialists(approved=True)
        self.missions = CollaborativeMission(self.colony)

    def test_four_calls_and_persisted_review_pending(self):
        client = FakeClient()
        result = self.missions.execute("Investigate solar energy", client=client, model="fake")
        self.assertEqual(result["model_calls"], 4)
        self.assertEqual(len(client.calls), 4)
        self.assertEqual([s["role"] for s in result["stages"]],
                         ["planner", "researcher", "reviewer", "synthesis"])
        self.assertEqual(result["status"], "review_pending")
        self.assertEqual(self.missions.get(result["id"])["stages"], result["stages"])
        self.assertIn("Result 2", client.calls[2][2])
        self.assertIn("Result 3", client.calls[3][2])

    def test_requires_reviewer_and_nonempty_task(self):
        with self.assertRaises(ValueError):
            self.missions.execute(" ", client=FakeClient(), model="fake")
        with self.colony._db() as db:
            db.execute("UPDATE colony_agents SET state='inactive' WHERE role='evidence-reviewer'")
        with self.assertRaises(RuntimeError):
            self.missions.execute("Valid", client=FakeClient(), model="fake")

    def test_model_failure_does_not_write_completed_mission(self):
        class BrokenClient:
            def chat(self, model, system, prompt):
                raise RuntimeError("Provider down")
        with self.assertRaises(RuntimeError):
            self.missions.execute("Valid", client=BrokenClient(), model="fake")
        with self.colony._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM colony_missions").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
