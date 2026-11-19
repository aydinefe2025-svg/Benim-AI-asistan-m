"""Fail-closed output protection for the legacy offline customer CSV CLI."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "battery_curve_audit"))
import customer_preflight as product


class CustomerOutputSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.manifest = self.root / "manifest.json"
        entries = []
        for cell, initial in (("A", "3.6"), ("B", "3.3"), ("C", "3.0")):
            path = self.root / (cell + ".csv")
            path.write_text(f"Timestamp [h],Voltage [V]\n0,{initial}\n1,{initial}\n",
                            encoding="utf-8")
            entries.append({"path": path.name, "cell": cell, "mode": "dchg"})
        self.manifest.write_text(json.dumps({"schema": product.SCHEMA,
                                             "files": entries}), encoding="utf-8")
        self.source = self.root / "A.csv"
        self.original_source = self.source.read_bytes()
        self.original_manifest = self.manifest.read_bytes()

    def run_cli(self, report, split=None):
        args = ["customer_preflight.py", "--manifest", str(self.manifest),
                "--report", str(report)]
        if split is not None:
            args.extend(["--split", str(split)])
        with mock.patch.object(sys, "argv", args):
            return product.main()

    def test_report_cannot_replace_source_csv(self):
        with self.assertRaisesRegex(ValueError, "output|overwrite|source|collision"):
            self.run_cli(self.source)
        self.assertEqual(self.source.read_bytes(), self.original_source)

    def test_split_cannot_replace_source_csv(self):
        report = self.root / "report.json"
        with self.assertRaisesRegex(ValueError, "output|overwrite|source|collision"):
            product.write_new_reports([(report, {"review": 1}), (self.source, {"unsafe": 1})], [self.manifest, self.source])
        self.assertEqual(self.source.read_bytes(), self.original_source)
        self.assertFalse(report.exists(), "report must not be left after rejected split")

    def test_report_cannot_replace_manifest(self):
        with self.assertRaisesRegex(ValueError, "output|overwrite|source|collision"):
            self.run_cli(self.manifest)
        self.assertEqual(self.manifest.read_bytes(), self.original_manifest)

    def test_existing_report_never_overwritten(self):
        report = self.root / "report.json"
        report.write_bytes(b"PREEXISTING_REPORT")
        with self.assertRaisesRegex(ValueError, "output|overwrite|existing|collision"):
            self.run_cli(report)
        self.assertEqual(report.read_bytes(), b"PREEXISTING_REPORT")

    def test_report_and_split_same_path_rejected(self):
        report = self.root / "report.json"
        with self.assertRaisesRegex(ValueError, "output|collision|duplicate"):
            product.write_new_reports([(report, {"a": 1}), (report, {"b": 1})], [self.manifest, self.source])
        self.assertFalse(report.exists())

    def test_report_symlink_to_source_rejected(self):
        alias = self.root / "alias.json"
        try:
            alias.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable on this runner")
        with self.assertRaisesRegex(ValueError, "output|overwrite|source|collision"):
            self.run_cli(alias)
        self.assertEqual(self.source.read_bytes(), self.original_source)

    def test_missing_split_parent_rejected_without_report(self):
        report = self.root / "report.json"
        split = self.root / "nonexistent" / "split.json"
        with self.assertRaisesRegex(ValueError, "parent|directory|output"):
            product.write_new_reports([(report, {"a": 1}), (split, {"b": 1})], [self.manifest, self.source])
        self.assertFalse(report.exists())

    def test_new_read_only_output_is_private_and_reproducible(self):
        report = self.root / "report.json"
        split = self.root / "split.json"
        self.run_cli(report)
        self.assertTrue(report.is_file())
        self.assertFalse(split.exists(), "legacy CLI never issues a split")
        result = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(result["trace_count"], 3)
        self.assertEqual(self.source.read_bytes(), self.original_source)
        self.assertEqual(self.manifest.read_bytes(), self.original_manifest)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(report.stat().st_mode), 0o600)

    def test_legacy_split_rejected_without_any_output(self):
        report = self.root / "report.json"
        split = self.root / "split.json"
        with self.assertRaisesRegex(ValueError, "legacy.*--split"):
            self.run_cli(report, split)
        self.assertFalse(report.exists())
        self.assertFalse(split.exists())

    def test_failure_during_second_write_rolls_back_first(self):
        report = self.root / "report.json"
        split = self.root / "split.json"
        real_open = os.open
        def simulate_disk_failure(path, flags, mode=0o777):
            if Path(path) == split:
                raise OSError("simulated full disk on split output")
            return real_open(path, flags, mode)
        with mock.patch.object(product.os, "open", side_effect=simulate_disk_failure):
            with self.assertRaisesRegex(OSError, "simulated full disk"):
                product.write_new_reports([(report, {"a": 1}), (split, {"b": 1})], [self.source, self.manifest])
        self.assertFalse(report.exists(), "first output must be rolled back")
        self.assertFalse(split.exists(), "no partial split output")
        self.assertEqual(self.source.read_bytes(), self.original_source)


if __name__ == "__main__":
    unittest.main()
