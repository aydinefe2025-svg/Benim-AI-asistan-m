import json
import tempfile
import unittest
from pathlib import Path
from scripts.validate_research_archive import validate, EXPECTED_TOPICS

class ArchiveValidationTests(unittest.TestCase):
    def test_valid_report(self):
        report = {"generated_at": "2026-11-02T00:00:00Z", "verified": False,
                  "topics": {k: {"status": "found", "sources": [
                      {"title": "Example", "url": "https://en.wikipedia.org/wiki/Example"}
                  ]} for k in EXPECTED_TOPICS}}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "report.json"
            p.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(validate(p), [])
            report["topics"]["robotics"]["sources"] = []
            p.write_text(json.dumps(report), encoding="utf-8")
            self.assertTrue(validate(p))
    def test_false_verification_is_required(self):
        report = {"generated_at": "2026-11-02", "verified": True, "topics": {}}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "report.json"
            p.write_text(json.dumps(report), encoding="utf-8")
            self.assertIn("source leads must not claim independent verification", validate(p))
