import tempfile
import json
import unittest
from pathlib import Path
from core.agent_colony import AgentColony
from core.colony_restore import restore_empty_colony
from core.collaborative_mission import CollaborativeMission


class RestoreTests(unittest.TestCase):
    def test_restore_readback_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "colony.sqlite3")
            data = {"agents": [
                {"id":"parent","parent_id":None,"generation":0,"role":"research",
                 "instructions":"Research","state":"active","created_at":"2026-01-01"},
                {"id":"child","parent_id":"parent","generation":1,"role":"review",
                 "instructions":"Review","state":"active","created_at":"2026-01-02"}],
                "feedback": [], "reviews": []}
            self.assertEqual(restore_empty_colony(colony, data), 2)
            self.assertEqual(colony.get("child")["parent_id"], "parent")
            with self.assertRaises(RuntimeError):
                restore_empty_colony(colony, data)
            self.assertEqual(colony.get("parent")["role"], "research")

    def test_mission_snapshot_restores_and_reads_back(self):
        with tempfile.TemporaryDirectory() as directory:
            first = AgentColony(Path(directory) / "source.sqlite3")
            founder = first.create_founder("research", "Research")
            reviewer = first.spawn(founder, "evidence-reviewer", "Review", approved=True)
            first_missions = CollaborativeMission(first)
            class FakeClient:
                def __init__(self): self.calls = 0
                def chat(self, model, system, prompt):
                    self.calls += 1
                    return "stage-" + str(self.calls)
            record = first_missions.execute("Safe factual test",
                                            client=FakeClient(), model="fake")
            with first._db() as db:
                snapshot = {
                    "agents": [dict(x) for x in db.execute("SELECT * FROM colony_agents")],
                    "feedback": [dict(x) for x in db.execute("SELECT * FROM colony_feedback")],
                    "reviews": [],
                    "missions": [dict(x) for x in db.execute("SELECT * FROM colony_missions")],
                }
            target = AgentColony(Path(directory) / "restored.sqlite3")
            self.assertEqual(restore_empty_colony(target, snapshot), 2)
            restored = CollaborativeMission(target).get(record["id"])
            self.assertEqual(restored["task"], record["task"])
            self.assertEqual(restored["stages"], record["stages"])
            self.assertEqual(restored["status"], "review_pending")
            with self.assertRaises(RuntimeError):
                restore_empty_colony(target, snapshot)

    def test_invalid_mission_prevents_partial_restoration(self):
        with tempfile.TemporaryDirectory() as directory:
            target = AgentColony(Path(directory) / "target.sqlite3")
            snapshot = {
                "agents": [{
                    "id": "founder", "parent_id": None, "generation": 0,
                    "role": "research", "instructions": "Research",
                    "state": "active", "created_at": "2026-01-01"}],
                "feedback": [], "reviews": [],
                "missions": [{
                    "id": "mission1", "task": "Check", "stages":
                    json.dumps([{"role": "planner", "agent_id": "missing", "output": "x"}]),
                    "status": "review_pending", "created_at": "2026-01-01"}],
            }
            with self.assertRaises(ValueError):
                restore_empty_colony(target, snapshot)
            with target._db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0], 0)

    def test_reject_missing_parent_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "colony.sqlite3")
            bad = {"agents":[{"id":"a","parent_id":"missing","generation":1,
                   "role":"research","instructions":"Research","state":"active",
                   "created_at":"2026-01-01"}],"feedback":[],"reviews":[]}
            with self.assertRaises(ValueError):
                restore_empty_colony(colony, bad)
            with colony._db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0],0)


if __name__ == "__main__":
    unittest.main()
