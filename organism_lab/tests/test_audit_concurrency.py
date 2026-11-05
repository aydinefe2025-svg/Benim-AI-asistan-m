"""Check multiple concurrent writers cannot fork the audit digest chain."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from organism_lab.audit_store import append_audit, read_audit


class AuditConcurrencyTests(unittest.TestCase):
    def test_concurrent_writers_preserve_chain(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "audit.jsonl"
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda index: append_audit(path, {
                    "task": f"task-{index}", "status": "checked"}), range(40)))
            stored = read_audit(path)
            self.assertEqual(len(stored), 40)
            self.assertEqual({r["digest"] for r in stored}, {r["digest"] for r in results})


if __name__ == "__main__":
    unittest.main()
