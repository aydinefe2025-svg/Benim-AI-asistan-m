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
            knowledge_store=self.knowledge, scientific_lookup=lambda *_args, **_kwargs: [],
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
            scientific_lookup=lambda *_args, **_kwargs: [],
        )
        result = orchestrator.run("A research question", web_search=True)
        self.assertEqual(result["search_count"], "1")
        self.assertIn("source pages not fetched", result["report"])
        self.assertIn("A discovery snippet.", result["report"])
        sources = self.knowledge.list_sources()
        self.assertEqual(len(sources), 1)
        self.assertIn("not fetched or verified", sources[0]["notes"])

    def test_opt_in_search_adds_crossref_metadata_without_claiming_it_was_read(self):
        def crossref(query, limit=3):
            self.assertEqual(query, "A research question")
            self.assertEqual(limit, 3)
            return [{"title": "Relevant paper", "url": "https://doi.org/10.1234/example",
                     "doi": "10.1234/example", "publisher": "Example Press",
                     "published_at": "2025-04-03", "verified": False}]

        orchestrator = ResearchOrchestrator(
            self.client, task_store=self.store, output_dir=self.out_dir,
            knowledge_store=self.knowledge, search_client=FakeSearch(),
            scientific_lookup=crossref,
        )
        result = orchestrator.run("A research question", web_search=True)
        self.assertEqual(result["search_count"], "2")
        self.assertIn("Crossref metadata only", result["report"])
        self.assertIn("primary-source review required", result["report"])
        self.assertIn("Relevant paper", result["report"])
        self.assertIn("Search lead only", self.knowledge.list_sources()[0]["notes"])

    def test_crossref_failure_keeps_ordinary_web_search_results(self):
        def broken_crossref(*_args, **_kwargs):
            raise OSError("private host detail")

        orchestrator = ResearchOrchestrator(
            self.client, task_store=self.store, output_dir=self.out_dir,
            search_client=FakeSearch(), scientific_lookup=broken_crossref,
        )
        result = orchestrator.run("A research question", web_search=True)
        self.assertEqual(result["search_count"], "1")
        self.assertEqual(result["search_error"], "OSError")
        self.assertNotIn("private host detail", result["report"])

    def test_empty_question_rejected(self):
        with self.assertRaises(ValueError):
            self.orchestrator.run("   ")
        self.assertEqual(self.store.list(), [])


if __name__ == "__main__":
    unittest.main()
