import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.continuous_colony import ContinuousColony
from scripts.verify_cano_restore import verify_restored_state


class ColonyRestoreTests(unittest.TestCase):
    def test_valid_prior_state_readback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "colony.sqlite3"
            colony = ContinuousColony(str(path))
            colony.initialize()
            tick = colony.tick([{"id": "founder", "generation": 0}])
            result = verify_restored_state(path)
            self.assertEqual(result["db_integrity"], "ok")
            self.assertEqual(result["stored_ticks"], 1)
            self.assertEqual(result["last_tick_id"], tick["tick_id"])

    def test_missing_database_fails_closed_without_creating_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "missing.sqlite3"
            with self.assertRaises(FileNotFoundError):
                verify_restored_state(path)
            self.assertFalse(path.exists())

    def test_corrupt_database_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "broken.sqlite3"
            path.write_bytes(b"not a sqlite database")
            with self.assertRaises(sqlite3.DatabaseError):
                verify_restored_state(path)

    def test_corrupted_candidate_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "colony.sqlite3"
            colony = ContinuousColony(str(path))
            colony.initialize()
            colony.tick([{"id": "founder"}])
            with sqlite3.connect(path) as db:
                db.execute("UPDATE colony_tick SET candidates='[bad' WHERE tick_id=1")
            with self.assertRaises(json.JSONDecodeError):
                verify_restored_state(path)


if __name__ == "__main__":
    unittest.main()
