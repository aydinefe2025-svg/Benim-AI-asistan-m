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
            self.assertEqual(data["mode"], "bounded_virtual_reproduction_with_held_out_validation")
            self.assertEqual(len(data["cycle"]["candidates"]), 3)
            self.assertEqual(data["cycle"]["activated"], 0)
            self.assertEqual(data["virtual_generation"]["generation_id"], data["verified_tick_id"])
            self.assertIn(data["virtual_generation"]["lesson_status"], {"transferred", "rejected"})
            agents = data["specialist_agents"]
            self.assertEqual(agents["status"], "passed")
            self.assertEqual(agents["launched"], 4)
            self.assertEqual(
                {agent["role"] for agent in agents["roles"]},
                {"evidence", "generation", "continuity", "security"},
            )
            self.assertTrue(all(agent["model_calls"] == 0 for agent in agents["roles"]))

    def test_second_invocation_continues_the_same_database_history(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "out.json"
            database = Path(temp) / "cycle.sqlite3"
            env = os.environ.copy()
            env["CANO_CYCLE_OUTPUT"] = str(output)
            env["CANO_CYCLE_DB"] = str(database)
            for expected_tick in (1, 2):
                subprocess.run(
                    [sys.executable, "-m", "scripts.cano_colony_cycle"],
                    env=env, capture_output=True, text=True, check=True,
                )
                data = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(data["verified_tick_id"], expected_tick)
                self.assertEqual(data["continuity"]["increment_verified"], True)
                self.assertEqual(
                    data["continuity"]["previous_tick_id"],
                    expected_tick - 1 if expected_tick > 1 else None,
                )


if __name__ == "__main__":
    unittest.main()
