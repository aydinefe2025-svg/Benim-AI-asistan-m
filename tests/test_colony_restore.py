import tempfile
import unittest
from pathlib import Path
from core.agent_colony import AgentColony
from core.colony_restore import restore_empty_colony


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
