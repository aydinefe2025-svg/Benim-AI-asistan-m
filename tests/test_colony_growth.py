import tempfile
from concurrent.futures import ThreadPoolExecutor
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

    def test_concurrent_growth_does_not_duplicate_specialists(self):
        with tempfile.TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "agents.db", max_agents=12)
            colony.create_founder("research", "Careful research")
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(
                    lambda _: colony.grow_specialists(approved=True, batch_size=3),
                    range(2)))
            self.assertEqual(sum(map(len, results)), 6)
            with colony._db() as db:
                roles = [row["role"] for row in db.execute(
                    "SELECT role FROM colony_agents").fetchall()]
            self.assertEqual(len(roles), 7)
            self.assertEqual(len(set(roles)), 7)
            self.assertEqual(colony.grow_specialists(approved=True), [])

    def test_invalid_batch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "agents.db")
            colony.create_founder("research", "Careful research")
            for value in (0, 6, True, "3"):
                with self.assertRaises(ValueError):
                    colony.grow_specialists(approved=True, batch_size=value)


if __name__ == "__main__":
    unittest.main()
