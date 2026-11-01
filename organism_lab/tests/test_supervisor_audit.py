from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from organism_lab.audit_store import read_audit
from organism_lab.supervisor import Supervisor

class SupervisorAuditTests(unittest.TestCase):
    def test_verified_and_failed_results_persist(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "audit.jsonl"
            result = Supervisor().run(
                [("research", "study"), ("code", "build")],
                {"research": lambda task: "report", "code": lambda task: ""},
                {"research": lambda task, output: "checked", "code": lambda task, output: "checked"},
                audit_path=path,
            )
            self.assertEqual((result["verified"], result["failed"]), (1, 1))
            saved = read_audit(path)
            self.assertEqual([record["status"] for record in saved], ["verified", "failed"])
            self.assertEqual(saved[1]["result"]["attempts"], 2)

    def test_without_audit_path_does_not_write(self):
        with TemporaryDirectory() as temp:
            Supervisor().run([("research", "study")],
                             {"research": lambda task: "report"},
                             {"research": lambda task, output: "checked"})
            self.assertEqual(list(Path(temp).iterdir()), [])

if __name__ == "__main__":
    unittest.main()
