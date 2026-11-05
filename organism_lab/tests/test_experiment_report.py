import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from organism_lab.experiment_report import build_documents, generate_report, verify_report


class ExperimentReportTests(unittest.TestCase):
    def test_generates_verifiable_bundle(self):
        with TemporaryDirectory() as folder:
            summary = generate_report(folder)
            self.assertEqual(summary["runs"], 12)
            self.assertEqual(len(summary["experiments"]), 12)
            self.assertTrue(verify_report(folder)["verified"])
            manifest = json.loads((Path(folder) / "experiment_manifest.json").read_text())
            self.assertEqual(len(manifest["checksums"]), 2)

    def test_detects_tampered_results(self):
        with TemporaryDirectory() as folder:
            generate_report(folder)
            file = Path(folder) / "experiment_results.json"
            file.write_bytes(file.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                verify_report(folder)

    def test_detects_modified_bundle_even_with_updated_checksum(self):
        with TemporaryDirectory() as folder:
            generate_report(folder)
            root = Path(folder)
            file = root / "experiment_summary.json"
            report = json.loads(file.read_text())
            report["runs"] = 999
            import hashlib
            from organism_lab.experiment_report import _json_bytes
            altered = _json_bytes(report)
            file.write_bytes(altered)
            manifest_path = root / "experiment_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["checksums"][file.name] = hashlib.sha256(altered).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Non-reproducible"):
                verify_report(folder)

    def test_results_are_stable(self):
        self.assertEqual(build_documents(), build_documents())


if __name__ == "__main__":
    unittest.main()
