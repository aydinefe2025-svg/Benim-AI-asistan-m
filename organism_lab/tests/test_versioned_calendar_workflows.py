"""Ensure the real scheduled calendar uses a schema-aware V1/V2 readback."""
import unittest
from pathlib import Path

WORKFLOW=Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cano-digital-organism-calendar.yml"

class ScheduledVersionCompatibility(unittest.TestCase):
    def test_scheduled_workflow_verifies_v1_and_v2_through_schema_aware_reader(self):
        content=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('python -m organism_lab.versioned_calendar inspect --state-dir "$STATE_DIR"', content)
        self.assertNotIn('python -m organism_lab.genome_checkpoint verify "$STATE_DIR/genome-state.json"', content)

if __name__=="__main__":
    unittest.main()
