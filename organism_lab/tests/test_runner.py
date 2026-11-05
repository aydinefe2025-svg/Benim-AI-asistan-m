import json
import tempfile
import unittest
from pathlib import Path
from organism_lab.runner import main, report

class RunnerTests(unittest.TestCase):
    def test_report_reproducible(self):
        self.assertEqual(report(), report())
    def test_report_contains_sections(self):
        r = report(steps=2)
        self.assertIn("evolution", r)
        self.assertIn("lineage_summary", r)
        self.assertIn("shared_world", r)
    def test_output_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results" / "run.json"
            self.assertEqual(main(["--steps", "3", "--output", str(path)]), 0)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["parameters"]["steps"], 3)
    def test_csv_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "series.csv"
            self.assertEqual(main(["--steps", "3", "--csv", str(csv_path),
                                   "--output", str(Path(tmp) / "report.json")]), 0)
            rows = csv_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(rows), 5)
            self.assertNotIn(b"\r\r\n", csv_path.read_bytes())
            self.assertIn("population", rows[0])
    def test_invalid_steps(self):
        with self.assertRaises(ValueError):
            report(steps=-1)
    def test_no_resources(self):
        r = report(steps=10, energy=0, materials=0, resources=0)
        self.assertEqual(r["shared_world"]["robots"], 0)
        self.assertEqual(r["shared_world"]["births"], 0)
