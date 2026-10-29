import tempfile
import unittest
from pathlib import Path

from core.research_orchestrator import ResearchOrchestrator
from core.task_store import TaskStore


class FakeClient:
    def __init__(self):
        self.calls = []

    def chat(self, model, system, prompt, *, temperature=0.2):
        self.calls.append((model, system, prompt))
        return f"mock-output-{len(self.calls)}"


class ResearchOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.store = TaskStore(root / "tasks.sqlite3")
        self.out_dir = root / "reports"
        self.client = FakeClient()
        self.orchestrator = ResearchOrchestrator(
            self.client, task_store=self.store, output_dir=self.out_dir
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_three_passes_are_recorded_without_claiming_web_verification(self):
        result = self.orchestrator.run("Cezeri mekanizmalarının tarihsel etkisi")
        self.assertEqual(len(self.client.calls), 3)
        self.assertEqual(result["same_model_all_roles"], "true")
        self.assertIn("web araması yapmadı", result["report"])
        self.assertTrue(Path(result["report_path"]).exists())
        task = self.store.get(result["task_id"])
        self.assertEqual(task["status"], "done")
        self.assertTrue(any("Report artifact:" in item for item in task["evidence"]))

    def test_distinct_role_models_are_labelled(self):
        result = self.orchestrator.run(
            "Test sorusu", research_model="qwen3:8b",
            skeptic_model="reviewer:latest", synthesis_model="writer:latest",
        )
        self.assertEqual(result["same_model_all_roles"], "false")

    def test_empty_question_rejected(self):
        with self.assertRaises(ValueError):
            self.orchestrator.run("   ")
        self.assertEqual(self.store.list(), [])


if __name__ == "__main__":
    unittest.main()
