from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from organism_lab.audit_store import append_audit
from organism_lab.audit_recovery import assess_audit

class AuditRecoveryTests(unittest.TestCase):
    def test_intact_file(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "audit.jsonl"
            append_audit(path, {"task": "one", "status": "checked"})
            report = assess_audit(path)
            self.assertEqual((report["status"], report["valid_records"]), ("intact", 1))

    def test_corruption_preserves_valid_prefix_and_original(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "audit.jsonl"
            append_audit(path, {"task": "one", "status": "checked"})
            append_audit(path, {"task": "two", "status": "failed"})
            original = path.read_bytes().replace(b'"two"', b'"bad"')
            path.write_bytes(original)
            report = assess_audit(path)
            self.assertEqual((report["status"], report["first_bad_line"], report["valid_records"]),
                             ("damaged", 2, 1))
            self.assertEqual(path.read_bytes(), original)

    def test_truncated_tail(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "audit.jsonl"
            append_audit(path, {"task": "one", "status": "checked"})
            path.write_bytes(path.read_bytes().rstrip(b"\n"))
            self.assertEqual(assess_audit(path)["reason"], "incomplete_line")

    def test_missing_file(self):
        with TemporaryDirectory() as temp:
            self.assertEqual(assess_audit(Path(temp) / "missing.jsonl")["status"], "missing")

if __name__ == "__main__":
    unittest.main()
