import tempfile
import unittest
from pathlib import Path

from core.continuous_colony import ContinuousColony


class ContinuousColonyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "colony.sqlite")
        self.colony = ContinuousColony(self.path, max_active=4, max_candidates_per_tick=2)
        self.colony.initialize()

    def test_repeated_ticks_are_persisted(self):
        a = self.colony.tick([{"id": "founder", "generation": 0}])
        b = self.colony.tick([{"id": "founder", "generation": 0}])
        self.assertEqual(len(a["candidates"]), 2)
        self.assertEqual(a["activated"], 0)
        self.assertNotEqual(a["tick_id"], b["tick_id"])
        self.assertEqual(len(ContinuousColony(self.path).history()), 2)

    def test_capacity_prevents_unbounded_spawning(self):
        agents = [{"id": str(i), "generation": i} for i in range(4)]
        tick = self.colony.tick(agents)
        self.assertEqual(tick["state"], "no_capacity")
        self.assertEqual(tick["candidates"], [])

    def test_invalid_identities_rejected_without_write(self):
        with self.assertRaises(ValueError):
            self.colony.tick([{"id": "same"}, {"id": "same"}])
        self.assertEqual(self.colony.history(), [])

    def test_new_candidate_is_not_activated(self):
        tick = self.colony.tick([])
        self.assertTrue(all(c["status"] == "awaiting_validation" for c in tick["candidates"]))
        self.assertEqual(tick["activated"], 0)


if __name__ == "__main__":
    unittest.main()
