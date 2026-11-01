"""Regression tests for process restart and historical audit integrity."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from organism_lab.audit_store import append_audit, read_audit


class AuditRestartTests(unittest.TestCase):
    def test_reopen_preserves_chain_and_continues(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "audit.jsonl"
            first = append_audit(path, {"task": "before-restart", "status": "verified"})
            self.assertEqual(read_audit(path)[0]["digest"], first["digest"])
            second = append_audit(path, {"task": "after-restart", "status": "failed"})
            self.assertEqual(second["previous"], first["digest"])
            self.assertEqual(len(read_audit(path)), 2)

    def test_corrupt_history_blocks_new_append(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "audit.jsonl"
            append_audit(path, {"task": "first", "status": "verified"})
            append_audit(path, {"task": "second", "status": "verified"})
            damaged = path.read_text(encoding="utf-8").replace("first", "changed")
            path.write_text(damaged, encoding="utf-8")
            with self.assertRaises(ValueError):
                append_audit(path, {"task": "third", "status": "verified"})
            self.assertEqual(path.read_text(encoding="utf-8"), damaged)


if __name__ == "__main__":
    unittest.main()
