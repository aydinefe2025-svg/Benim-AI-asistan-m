import tempfile
import unittest
from pathlib import Path

from core.queen_coordinator import QueenCoordinator


class QueenFailoverTests(unittest.TestCase):
    def test_failover_fences_old_leader(self):
        with tempfile.TemporaryDirectory() as tmp:
            queens = QueenCoordinator(Path(tmp) / "queens.sqlite3")
            with self.assertRaises(PermissionError):
                queens.register("a")
            queens.register("a", authorized=True)
            queens.register("b", authorized=True)
            first = queens.acquire("a", ttl=10, at=100)
            self.assertEqual(first, 1)
            self.assertIsNone(queens.acquire("b", ttl=10, at=101))
            self.assertTrue(queens.valid("a", first, at=102))
            second = queens.acquire("b", ttl=10, at=111)
            self.assertEqual(second, 2)
            self.assertFalse(queens.valid("a", first, at=112))
            self.assertTrue(queens.valid("b", second, at=112))
            queens.relinquish("a", first)
            self.assertTrue(queens.valid("b", second, at=112))

    def test_unhealthy_and_unauthorized_nodes_cannot_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            queens = QueenCoordinator(Path(tmp) / "queens.sqlite3")
            with self.assertRaises(PermissionError):
                queens.acquire("unknown", at=10)
            queens.register("a", authorized=True)
            queens.set_health("a", False, authorized=True)
            with self.assertRaises(PermissionError):
                queens.acquire("a", at=10)
            with self.assertRaises(ValueError):
                queens.acquire("a", ttl=0, at=10)


if __name__ == "__main__":
    unittest.main()
