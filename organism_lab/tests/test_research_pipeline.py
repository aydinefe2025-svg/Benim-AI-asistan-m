from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from organism_lab.audit_store import append_audit, read_audit
from organism_lab.research_pipeline import run_pipeline

class ResearchPipelineTests(unittest.TestCase):
    def test_end_to_end_pipeline(self):
        with TemporaryDirectory() as temp:
            result = run_pipeline(temp)
            self.assertEqual(result["tasks"]["verified"], 3)
            self.assertEqual(result["tasks"]["failed"], 0)
            self.assertEqual(len(read_audit(Path(temp) / "tasks.jsonl")), 3)
            self.assertTrue((Path(temp) / "report.json").is_file())

    def test_corrupted_audit_prevents_new_work(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "tasks.jsonl"
            append_audit(path, {"task": "first", "status": "verified"})
            path.write_bytes(path.read_bytes().replace(b'"first"', b'"other"'))
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "Damaged audit"):
                run_pipeline(temp)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((Path(temp) / "report.json").exists())

if __name__ == "__main__":
    unittest.main()
