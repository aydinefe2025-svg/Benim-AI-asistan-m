import tempfile
from datetime import datetime, timedelta, timezone
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

    def test_model_failure_checkpoints_and_resume_skips_completed_stages(self):
        class FailingOnce:
            def __init__(self):
                self.calls = 0

            def chat(self, model, system, prompt):
                self.calls += 1
                if self.calls == 3:
                    raise RuntimeError("Provider down")
                return "Result " + str(self.calls)

        client = FailingOnce()
        with self.assertRaises(RuntimeError):
            self.missions.execute("Valid", client=client, model="fake")
        interrupted = self.missions.interrupted()
        self.assertEqual(len(interrupted), 1)
        self.assertEqual(interrupted[0]["status"], "blocked")
        partial = self.missions.get(interrupted[0]["id"])
        self.assertEqual([s["role"] for s in partial["stages"]],
                         ["planner", "researcher"])
        result = self.missions.resume(partial["id"], client=client, model="fake")
        self.assertEqual(result["status"], "review_pending")
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(client.calls, 5)
        self.assertEqual([s["output"] for s in result["stages"][:2]],
                         ["Result 1", "Result 2"])
        self.assertEqual(self.missions.resume(partial["id"], client=client,
                                               model="fake")["model_calls"], 0)
        self.assertEqual(client.calls, 5)
        self.assertEqual(self.missions.interrupted(), [])

    def test_stale_running_requires_recovery_before_resume(self):
        mission_id = "running-test"
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        with self.colony._db() as db:
            db.execute("INSERT INTO colony_missions VALUES (?,?,?,?,?)",
                       (mission_id, "Valid", "[]", "running", old_time))
        with self.assertRaises(RuntimeError):
            self.missions.resume(mission_id, client=FakeClient(), model="fake")
        recovered = self.missions.recover_stale(older_than_seconds=3600)
        self.assertEqual(recovered, [mission_id])
        result = self.missions.resume(mission_id, client=FakeClient(), model="fake")
        self.assertEqual(result["model_calls"], 4)
        self.assertEqual(result["status"], "review_pending")

    def test_recent_running_not_recovered_and_threshold_validated(self):
        with self.colony._db() as db:
            db.execute("INSERT INTO colony_missions VALUES (?,?,?,?,?)",
                       ("recent", "Valid", "[]", "running",
                        datetime.now(timezone.utc).isoformat()))
        self.assertEqual(self.missions.recover_stale(), [])
        with self.assertRaises(ValueError):
            self.missions.recover_stale(older_than_seconds=30)


if __name__ == "__main__":
    unittest.main()
