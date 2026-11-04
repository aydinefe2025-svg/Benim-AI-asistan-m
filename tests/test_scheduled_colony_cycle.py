import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
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


    def test_rejects_tampered_exact_tick_record(self):
        from core.continuous_colony import ContinuousColony
        from scripts import cano_colony_cycle

        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "cycle.sqlite3"
            output = Path(temp) / "out.json"
            original_tick = ContinuousColony.tick

            def tampered_tick(colony, agents):
                result = original_tick(colony, agents)
                with sqlite3.connect(db_path) as db:
                    db.execute(
                        "UPDATE colony_tick SET state='no_capacity' WHERE tick_id=?",
                        (result["tick_id"],),
                    )
                return result

            with patch.dict(os.environ, {
                "CANO_CYCLE_DB": str(db_path),
                "CANO_CYCLE_OUTPUT": str(output),
            }), patch.object(ContinuousColony, "tick", tampered_tick):
                with self.assertRaisesRegex(RuntimeError, "readback check"):
                    cano_colony_cycle.main()
            self.assertFalse(output.exists())


    def test_atomic_publication_preserves_previous_report_on_replace_failure(self):
        from scripts import cano_colony_cycle

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "out.json"
            output.write_text('{"previous": true}', encoding="utf-8")
            db_path = Path(temp) / "cycle.sqlite3"
            with patch.dict(os.environ, {
                "CANO_CYCLE_DB": str(db_path),
                "CANO_CYCLE_OUTPUT": str(output),
            }), patch.object(cano_colony_cycle.os, "replace", side_effect=OSError("simulated crash")):
                with self.assertRaisesRegex(OSError, "simulated crash"):
                    cano_colony_cycle.main()
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"previous": True})
            self.assertEqual(list(Path(temp).glob(".out.json.*.tmp")), [])
            with sqlite3.connect(db_path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM colony_tick").fetchone()[0], 1)



if __name__ == "__main__":
    unittest.main()
