import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from core.cli import main


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tempdir.name) / "cli.sqlite3")

    def tearDown(self):
        self.tempdir.cleanup()

    def invoke(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--db", self.db, *args])
        self.assertEqual(code, 0)
        return json.loads(output.getvalue())

    def test_task_add_and_list(self):
        created = self.invoke("task-add", "Build research index", "--goal", "Track sources")
        self.assertEqual(created["title"], "Build research index")
        tasks = self.invoke("task-list")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["status"], "planned")

    def test_source_and_claim_workflow(self):
        source = self.invoke("source-add", "https://example.org/paper", "Example paper")
        claim = self.invoke(
            "claim-add", "The example is testable", "--source-id", str(source["id"])
        )
        self.assertEqual(claim["status"], "unreviewed")
        claims = self.invoke("claim-list")
        self.assertEqual(len(claims), 1)


if __name__ == "__main__":
    unittest.main()
