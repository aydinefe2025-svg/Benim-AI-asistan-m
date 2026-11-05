import tempfile
import unittest
from pathlib import Path

from core.knowledge_store import KnowledgeStore
from core.research_orchestrator import ResearchOrchestrator
from core.task_store import TaskStore
from core.web_search import SearchResult


class FakeClient:
    def __init__(self):
        self.calls = []

    def chat(self, model, system, prompt, *, temperature=0.2):
        self.calls.append((model, system, prompt))
        return f"mock-output-{len(self.calls)}"


class FakeSearch:
    def search(self, query, max_results=5):
        return [SearchResult("Example source", "https://example.org/source", "A discovery snippet.", "example.org")]


class ResearchOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.store = TaskStore(root / "tasks.sqlite3")
        self.knowledge = KnowledgeStore(root / "tasks.sqlite3")
        self.out_dir = root / "reports"
        self.client = FakeClient()
        self.orchestrator = ResearchOrchestrator(
            self.client, task_store=self.store, output_dir=self.out_dir,
            knowledge_store=self.knowledge,
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_three_passes_are_recorded_without_claiming_web_verification(self):
        result = self.orchestrator.run("Cezeri mekanizmalarının tarihsel etkisi")
        self.assertEqual(len(self.client.calls), 3)
        self.assertEqual(result["same_model_all_roles"], "true")
        self.assertIn("Web search was not requested.", result["report"])
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


    def test_opt_in_search_is_recorded_as_snippet_not_verified_source(self):
        orchestrator = ResearchOrchestrator(
            self.client, task_store=self.store, output_dir=self.out_dir,
            knowledge_store=self.knowledge, search_client=FakeSearch(),
        )
        result = orchestrator.run("A research question", web_search=True)
        self.assertEqual(result["search_count"], "1")
        self.assertIn("source pages not fetched", result["report"])
        self.assertIn("A discovery snippet.", result["report"])
        sources = self.knowledge.list_sources()
        self.assertEqual(len(sources), 1)
        self.assertIn("not fetched or verified", sources[0]["notes"])

    def test_opted_in_provider_fallback_is_recorded_as_actual_model_for_all_roles(self):
        from core.fallback_chat_client import FallbackChatClient

        class UnavailableLocal:
            def chat(self, model, system, prompt, *, temperature=0.2):
                raise TimeoutError("local provider timed out")

        remote = FakeClient()
        failover = FallbackChatClient(
            UnavailableLocal(), fallback=remote, fallback_model="groq/gpt-oss",
            allow_fallback=True,
        )
        result = ResearchOrchestrator(
            failover, task_store=self.store, output_dir=self.out_dir,
        ).run("A bounded test question", research_model="qwen3:8b")

        self.assertEqual(len(remote.calls), 3)
        self.assertEqual(result["research_model"], "groq/gpt-oss")
        self.assertEqual(result["skeptic_model"], "groq/gpt-oss")
        self.assertEqual(result["synthesis_model"], "groq/gpt-oss")
        self.assertEqual(result["same_model_all_roles"], "true")
        self.assertIn("Araştırma modeli: groq/gpt-oss", result["report"])
        self.assertNotIn("Araştırma modeli: qwen3:8b", result["report"])

    def test_empty_question_rejected(self):
        with self.assertRaises(ValueError):
            self.orchestrator.run("   ")
        self.assertEqual(self.store.list(), [])


if __name__ == "__main__":
    unittest.main()
