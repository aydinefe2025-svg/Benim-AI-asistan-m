import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ScheduledColonyCycleTests(unittest.TestCase):
    def test_cycle_creates_auditable_proposal(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "out.json"
            env = os.environ.copy()
            env["CANO_CYCLE_OUTPUT"] = str(output)
            env["CANO_CYCLE_DB"] = str(Path(temp) / "cycle.sqlite3")
            result = subprocess.run(
                [sys.executable, "-m", "scripts.cano_colony_cycle"],
                env=env, capture_output=True, text=True, check=True,
            )
            self.assertEqual(json.loads(result.stdout)["activated"], 0)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "proposal_only")
            self.assertEqual(data["db_integrity"], "ok")
            self.assertEqual(data["stored_ticks"], 1)
            self.assertEqual(data["verified_tick_id"], data["cycle"]["tick_id"])
            self.assertEqual(len(data["cycle"]["candidates"]), 3)
            self.assertEqual(data["cycle"]["activated"], 0)


    def test_two_runs_reuse_database_without_activating_agents(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "out.json"
            db_path = Path(temp) / "cycle.sqlite3"
            env = os.environ.copy()
            env["CANO_CYCLE_OUTPUT"] = str(output)
            env["CANO_CYCLE_DB"] = str(db_path)
            ticks = []
            for expected_count in (1, 2):
                completed = subprocess.run(
                    [sys.executable, "-m", "scripts.cano_colony_cycle"],
                    env=env, capture_output=True, text=True, check=True,
                )
                summary = json.loads(completed.stdout)
                data = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(summary["activated"], 0)
                self.assertEqual(data["stored_ticks"], expected_count)
                self.assertEqual(data["db_integrity"], "ok")
                self.assertEqual(data["verified_tick_id"], data["cycle"]["tick_id"])
                self.assertEqual(data["cycle"]["activated"], 0)
                ticks.append(data["verified_tick_id"])
            self.assertEqual(ticks, [1, 2])


if __name__ == "__main__":
    unittest.main()
