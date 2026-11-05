import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from organism_lab.source_evidence import compile_evidence, export_evidence


def record(**changes):
    item = {"topic": "astronomy", "title": "Source", "source_url": "https://example.org/paper",
            "accessed_at": "2026-11-03T20:00:00Z", "claim": "A measured value",
            "assessment": "unverified"}
    item.update(changes)
    return item


class SourceEvidenceTests(unittest.TestCase):
    def test_deduplicates_identical_claims(self):
        report = compile_evidence([record(), record()])
        self.assertEqual(report["count"], 1)
        self.assertEqual(len(report["records"][0]["id"]), 64)

    def test_rejects_conflicting_duplicates(self):
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            compile_evidence([record(), record(title="Different")])

    def test_requires_evidence_for_supported_claim(self):
        with self.assertRaisesRegex(ValueError, "excerpt"):
            compile_evidence([record(assessment="supported")])
        self.assertEqual(compile_evidence([record(assessment="supported", evidence_excerpt="Observed text")])["count"], 1)

    def test_rejects_untrusted_urls_and_missing_fields(self):
        for bad in ("http://example.org", "file:///tmp/a", "https://user:password@example.org/a"):
            with self.subTest(url=bad), self.assertRaises(ValueError):
                compile_evidence([record(source_url=bad)])
        with self.assertRaises(ValueError):
            compile_evidence([record(claim="")])

    def test_atomic_export_preserves_old_report_on_failure(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "input.json"
            output = Path(temp) / "report.json"
            source.write_text(json.dumps([record()]), encoding="utf-8")
            self.assertEqual(export_evidence(source, output)["count"], 1)
            before = output.read_bytes()
            source.write_text(json.dumps([record(assessment="supported")]), encoding="utf-8")
            with self.assertRaises(ValueError):
                export_evidence(source, output)
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
