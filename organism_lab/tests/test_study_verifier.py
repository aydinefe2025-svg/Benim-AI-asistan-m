"""Fail-closed persistence and replay checks for numerical organism studies."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from organism_lab.reproduction_study import run_study, save_study
from organism_lab.study_verifier import verify_saved_study


class StudyVerifierTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.study = run_study(seeds=(0, 1, 2), steps=12, resource_levels=(0, 5))
        self.paths = save_study(self.study, self.directory.name,
                                model_commentary={"status": "not_requested", "text": ""})

    def test_reopens_and_recomputes_every_format(self):
        receipt = verify_saved_study(self.paths)
        self.assertTrue(receipt["verified"])
        self.assertEqual(receipt["observations"], 6)
        self.assertEqual(receipt["verified_files"], ["json", "csv", "sqlite"])
        self.assertEqual(len(receipt["json_sha256"]), 64)

    def test_rejects_tampered_json_even_when_sqlite_is_unchanged(self):
        path = Path(self.paths["json_path"])
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["results"][0]["mean_births"] += 999
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "independently"):
            verify_saved_study(self.paths)

    def test_rejects_tampered_csv(self):
        path = Path(self.paths["csv_path"])
        path.write_text(path.read_text(encoding="utf-8").replace("0,0,", "0,999,", 1),
                        encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "CSV"):
            verify_saved_study(self.paths)

    def test_rejects_corrupted_sqlite(self):
        with sqlite3.connect(self.paths["database_path"]) as conn:
            conn.execute("DELETE FROM studies WHERE study_id = ?", (self.paths["study_id"],))
        with self.assertRaisesRegex(ValueError, "SQLite"):
            verify_saved_study(self.paths)

    def test_rejects_missing_file(self):
        Path(self.paths["csv_path"]).unlink()
        with self.assertRaisesRegex(ValueError, "Unable"):
            verify_saved_study(self.paths)


if __name__ == "__main__":
    unittest.main()
