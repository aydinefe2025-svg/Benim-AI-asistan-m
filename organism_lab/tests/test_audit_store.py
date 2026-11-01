import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from organism_lab.audit_store import append_audit, read_audit

class AuditStoreTests(unittest.TestCase):
    def test_roundtrip_and_chain(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "audit.jsonl"
            first = append_audit(path, {"task": "scan", "status": "verified", "evidence": "ok"})
            second = append_audit(path, {"task": "scan2", "status": "failed", "evidence": "error"})
            self.assertEqual(len(read_audit(path)), 2)
            self.assertEqual(second["previous"], first["digest"])

    def test_detects_tampering(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "audit.jsonl"
            append_audit(path, {"task": "scan", "status": "verified"})
            path.write_text(path.read_text().replace("scan", "fake"), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_audit(path)

    def test_rejects_unverified_status(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "audit.jsonl"
            with self.assertRaises(ValueError):
                append_audit(path, {"task": "scan", "status": "queued"})
            self.assertFalse(path.exists())

if __name__ == "__main__":
    unittest.main()
