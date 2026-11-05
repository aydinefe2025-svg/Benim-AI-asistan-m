"""Integration checks for colony feedback retrieval against a no-memory baseline."""
import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony
from core.benchmark_harness import BenchmarkCase, run_colony_memory_benchmark


class MemoryAwareFakeClient:
    def __init__(self):
        self.prompts = []

    def chat(self, model, system, prompt):
        self.prompts.append(prompt)
        has_approved_lesson = "Prefer primary evidence" in prompt
        question_one = "Question one" in prompt
        if has_approved_lesson:
            return "correct" if question_one else "wrong"
        return "wrong" if question_one else "correct"


class ColonyMemoryBenchmarkTests(unittest.TestCase):
    def test_uses_accepted_lessons_and_reports_per_case_regression_without_text(self):
        with tempfile.TemporaryDirectory() as folder:
            colony = AgentColony(Path(folder) / "colony.sqlite3")
            agent = colony.create_founder("researcher", "Be precise.")
            colony.feedback(agent, "old", "Unreviewed guess", "evidence:rejected",
                            accepted=False)
            colony.feedback(agent, "old", "Prefer primary evidence",
                            "evidence:approved-1", accepted=True)
            client = MemoryAwareFakeClient()
            cases = (
                BenchmarkCase("case-1", "Question one", "correct"),
                BenchmarkCase("case-2", "Question two", "correct"),
            )

            result = run_colony_memory_benchmark(
                colony, agent, cases, client=client, model="local-test",
                source_refs=("fixture:paired-memory",), safety_pass=True,
            )

            self.assertEqual(result["baseline"].passed, 1)
            self.assertEqual(result["candidate"].passed, 1)
            self.assertEqual(result["improved_case_ids"], ["case-1"])
            self.assertEqual(result["regressed_case_ids"], ["case-2"])
            self.assertEqual(result["memory_lessons_available"], 1)
            self.assertEqual(result["comparison"], "accepted_feedback_retrieval_only")
            self.assertFalse(result["model_weights_updated"])
            self.assertTrue(all("Prefer primary evidence" not in prompt
                                for prompt in client.prompts[::2]))
            self.assertTrue(any("Prefer primary evidence" in prompt
                                for prompt in client.prompts[1::2]))
            self.assertTrue(all("Unreviewed guess" not in prompt
                                for prompt in client.prompts))
            self.assertNotIn("Question one", repr(result))
            self.assertNotIn("correct", repr(result))

    def test_rejects_oversized_suite_before_any_model_call(self):
        with tempfile.TemporaryDirectory() as folder:
            colony = AgentColony(Path(folder) / "colony.sqlite3")
            agent = colony.create_founder("researcher", "Be precise.")
            client = MemoryAwareFakeClient()
            cases = tuple(BenchmarkCase(f"case-{i}", f"Question {i}", "ok")
                          for i in range(11))

            with self.assertRaisesRegex(ValueError, "40 model calls"):
                run_colony_memory_benchmark(
                    colony, agent, cases, client=client, model="local-test",
                    source_refs=("fixture:bounded",),
                )

            self.assertEqual(client.prompts, [])

    def test_agent_run_can_disable_memory_without_changing_persisted_lessons(self):
        with tempfile.TemporaryDirectory() as folder:
            colony = AgentColony(Path(folder) / "colony.sqlite3")
            agent = colony.create_founder("researcher", "Be precise.")
            colony.feedback(agent, "old", "Use accepted evidence",
                            "evidence:1", accepted=True)
            client = MemoryAwareFakeClient()

            baseline = colony.run(
                agent, "Question one", client=client, model="local-test",
                include_lessons=False,
            )

            self.assertEqual(baseline["lessons_used"], 0)
            self.assertEqual(len(colony.lessons(agent)), 1)
            with self.assertRaises(ValueError):
                colony.run(agent, "Question", client=client, model="local-test",
                           include_lessons="yes")


if __name__ == "__main__":
    unittest.main()
