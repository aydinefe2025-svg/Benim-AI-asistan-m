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

    def test_new_report_requires_consistent_unverified_scholarly_leads(self):
        lead = {"title": "A study", "doi": "10.1234/example", "url": "https://doi.org/10.1234/example",
                "verified": False, "stage": "source_lead", "retrieval": "publisher_metadata",
                "primary_source_review": "required", "confidence": "unassessed"}
        report = {"generated_at": "2026-11-09T00:00:00Z", "verified": False,
                  "topics": {k: {"status": "found", "sources": [
                      {"title": "Example", "url": "https://en.wikipedia.org/wiki/Example"}
                  ]} for k in EXPECTED_TOPICS},
                  "scholarly_topics": {k: {"status": "metadata_only", "verified": False,
                                           "sources": [dict(lead)]} for k in EXPECTED_TOPICS}}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "report.json"
            p.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(validate(p, require_scholarly=True), [])
            report["scholarly_topics"]["robotics"]["sources"][0]["url"] = "https://evil.invalid/10.1234/example"
            p.write_text(json.dumps(report), encoding="utf-8")
            self.assertIn("robotics: DOI URL does not match DOI", validate(p, require_scholarly=True))

    def test_legacy_reports_remain_valid_but_new_reports_require_scholarly_section(self):
        report = {"generated_at": "2026-11-02T00:00:00Z", "verified": False,
                  "topics": {k: {"status": "found", "sources": [
                      {"title": "Example", "url": "https://en.wikipedia.org/wiki/Example"}
                  ]} for k in EXPECTED_TOPICS}}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "report.json"
            p.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(validate(p), [])
            self.assertIn("missing or invalid scholarly topics", validate(p, require_scholarly=True))

    def test_verified_scholarly_claims_are_rejected_even_with_a_doi(self):
        report = {"generated_at": "2026-11-09", "verified": False,
                  "topics": {k: {"status": "found", "sources": [
                      {"title": "Example", "url": "https://en.wikipedia.org/wiki/Example"}
                  ]} for k in EXPECTED_TOPICS},
                  "scholarly_topics": {k: {"status": "metadata_only", "verified": True, "sources": []}
                                       for k in EXPECTED_TOPICS}}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "report.json"
            p.write_text(json.dumps(report), encoding="utf-8")
            self.assertIn("neutron_star_eos: scholarly metadata must remain unverified",
                          validate(p, require_scholarly=True))

    def test_malformed_url_values_fail_validation_without_crashing(self):
        report = {"generated_at": "2026-11-09", "verified": False,
                  "topics": {k: {"status": "found", "sources": [
                      {"title": "Example", "url": 123}
                  ]} for k in EXPECTED_TOPICS}}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "report.json"
            p.write_text(json.dumps(report), encoding="utf-8")
            self.assertIn("robotics: invalid source URL", validate(p))
    def test_false_verification_is_required(self):
        report = {"generated_at": "2026-11-02", "verified": True, "topics": {}}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "report.json"
            p.write_text(json.dumps(report), encoding="utf-8")
            self.assertIn("source leads must not claim independent verification", validate(p))

