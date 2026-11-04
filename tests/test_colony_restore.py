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

    def test_partial_mission_restores_blocked_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = AgentColony(Path(directory) / "source.db")
            founder = source.create_founder("research", "Research")
            source.spawn(founder, "evidence-reviewer", "Review", approved=True)
            missions = CollaborativeMission(source)
            class FailSecond:
                def __init__(self): self.calls = 0
                def chat(self, model, system, prompt):
                    self.calls += 1
                    if self.calls == 2:
                        raise RuntimeError("Provider interrupted")
                    return "stage-" + str(self.calls)
            with self.assertRaises(RuntimeError):
                missions.execute("Safe test", client=FailSecond(), model="fake")
            with source._db() as db:
                snapshot = {
                    "agents": [dict(r) for r in db.execute("SELECT * FROM colony_agents")],
                    "feedback": [], "reviews": [],
                    "missions": [dict(r) for r in db.execute("SELECT * FROM colony_missions")],
                }
            self.assertEqual(snapshot["missions"][0]["status"], "blocked")
            target = AgentColony(Path(directory) / "restored.db")
            self.assertEqual(restore_empty_colony(target, snapshot), 2)
            saved = CollaborativeMission(target).get(snapshot["missions"][0]["id"])
            self.assertEqual(len(saved["stages"]), 1)
            class Fake:
                def __init__(self): self.calls = 0
                def chat(self, model, system, prompt):
                    self.calls += 1
                    return "continued-" + str(self.calls)
            client = Fake()
            resumed = CollaborativeMission(target).resume(saved["id"], client=client,
                                                           model="fake")
            self.assertEqual(resumed["model_calls"], 3)
            self.assertEqual(client.calls, 3)
            self.assertEqual(resumed["stages"][0]["output"], "stage-1")

    def test_imported_running_mission_becomes_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            target = AgentColony(Path(directory) / "restored.db")
            snapshot = {
                "agents": [{
                    "id": "founder", "parent_id": None, "generation": 0,
                    "role": "research", "instructions": "Research",
                    "state": "active", "created_at": "2026-01-01"}],
                "feedback": [], "reviews": [],
                "missions": [{"id": "run1", "task": "Research", "stages": "[]",
                              "status": "running", "created_at": "2026-01-01"}]
            }
            self.assertEqual(restore_empty_colony(target, snapshot), 1)
            self.assertEqual(CollaborativeMission(target).get("run1")["status"],
                             "blocked")

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
