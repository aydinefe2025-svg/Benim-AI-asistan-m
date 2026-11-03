import tempfile
import unittest
from pathlib import Path
from core.agent_colony import AgentColony


class GrowthTests(unittest.TestCase):
    def test_authorized_growth_is_bounded_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "agents.db", max_agents=5)
            founder = colony.create_founder("research", "Careful research")
            with self.assertRaises(PermissionError):
                colony.grow_specialists()
            first = colony.grow_specialists(approved=True, batch_size=3)
            second = colony.grow_specialists(approved=True, batch_size=3)
            third = colony.grow_specialists(approved=True, batch_size=3)
            self.assertEqual((len(first), len(second), len(third)), (3, 1, 0))
            self.assertEqual(colony.get(first[0])["parent_id"], founder)
            with colony._db() as db:
                rows = db.execute("SELECT role FROM colony_agents").fetchall()
            self.assertEqual(len({row["role"] for row in rows}), 5)

    def test_invalid_batch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "agents.db")
            colony.create_founder("research", "Careful research")
            for value in (0, 6, True, "3"):
                with self.assertRaises(ValueError):
                    colony.grow_specialists(approved=True, batch_size=value)


if __name__ == "__main__":
    unittest.main()
