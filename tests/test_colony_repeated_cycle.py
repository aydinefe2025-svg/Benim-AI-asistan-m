"""Regression: sequential cycles retain and verify the correct SQLite tick."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ColonyRepeatedCycleTests(unittest.TestCase):
    def test_two_cycles_verify_second_tick_without_activating_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "colony.sqlite3"
            report = Path(directory) / "audit.json"
            env = os.environ.copy()
            env["CANO_CYCLE_DB"] = str(db)
            env["CANO_CYCLE_OUTPUT"] = str(report)
            for tick in (1, 2):
                run = subprocess.run(
                    [sys.executable, "-m", "scripts.cano_colony_cycle"],
                    env=env, capture_output=True, text=True, check=True,
                )
                stdout = json.loads(run.stdout)
                audit = json.loads(report.read_text(encoding="utf-8"))
                self.assertEqual(stdout["tick_id"], tick)
                self.assertEqual(audit["verified_tick_id"], tick)
                self.assertEqual(audit["stored_ticks"], tick)
                self.assertEqual(audit["db_integrity"], "ok")
                self.assertEqual(audit["cycle"]["activated"], 0)


if __name__ == "__main__":
    unittest.main()
