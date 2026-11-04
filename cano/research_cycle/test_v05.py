import unittest, tempfile, json, sqlite3
from pathlib import Path
import core
class V05Tests(unittest.TestCase):
    def test_empty_audit_is_not_success(self):
        with tempfile.TemporaryDirectory() as d:
            c=core.connect(Path(d)/"test.db")
            self.assertFalse(core.evidence_audit(c)["passed"])
            c.close()
    def test_failed_task_blocks_audit(self):
        with tempfile.TemporaryDirectory() as d:
            c=core.connect(Path(d)/"test.db")
            core.add(c,"sift_synthetic")
            self.assertFalse(core.evidence_audit(c)["passed"])
            c.close()
    def test_manifest_matches(self):
        data=json.loads((core.ROOT/"trusted_script_manifest.json").read_text())
        self.assertTrue(core.verify_manifest(data))
    def test_manifest_detects_tamper(self):
        data=json.loads((core.ROOT/"trusted_script_manifest.json").read_text())
        data["files"][0]["sha256"]="0"*64
        self.assertFalse(core.verify_manifest(data))
if __name__=="__main__": unittest.main()