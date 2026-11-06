"""Integration checks for colony feedback retrieval against a no-memory baseline."""
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from core.agent_colony import AgentColony
from core.benchmark_harness import (
    BenchmarkCase, parse_memory_benchmark_cases, run_colony_memory_benchmark,
)
from core.colony_panel import render_colony_panel


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


class BenchmarkPanelUI:
    def __init__(self, *, run_benchmark=False):
        self.sidebar = self
        self.session_state = {}
        self.run_benchmark = run_benchmark
        self.calls = []
        self.case_json = '[{"case_id":"one","prompt":"Question","expected":"answer"}]'

    def expander(self, *args, **kwargs): return nullcontext()
    def form(self, *args, **kwargs): return nullcontext()
    def caption(self, text): self.calls.append(("caption", text))
    def info(self, text): self.calls.append(("info", text))
    def warning(self, text): self.calls.append(("warning", text))
    def error(self, text): self.calls.append(("error", text))
    def success(self, text): self.calls.append(("success", text))
    def subheader(self, text): self.calls.append(("subheader", text))
    def write(self, *args, **kwargs): pass
    def rerun(self): pass
    def selectbox(self, label, options, **kwargs): return options[0]
    def text_input(self, label, **kwargs): return "reviewed-set-v1"
    def text_area(self, label, **kwargs):
        return self.case_json if label == "İnsan tarafından etiketlenmiş testler (JSON)" else ""
    def checkbox(self, label, **kwargs): return False
    def file_uploader(self, *args, **kwargs): return None
    def button(self, *args, **kwargs): return False
    def form_submit_button(self, label, **kwargs):
        if label == "Ders açık/kapalı karşılaştırmasını başlat" and self.run_benchmark:
            self.run_benchmark = False
            return True
        return False
    def download_button(self, *args, **kwargs): return None


class ColonyMemoryBenchmarkTests(unittest.TestCase):
    def test_panel_makes_no_provider_calls_until_user_starts_paired_run(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "colony.sqlite3"
            colony = AgentColony(path)
            agent = colony.create_founder("researcher", "Be precise.")
            colony.feedback(agent, "reviewed task", "Prefer primary evidence",
                            "review:case-1", accepted=True)

            for submit, expected_calls in ((False, 0), (True, 4)):
                ui = BenchmarkPanelUI(run_benchmark=submit)
                provider_prompts = []
                def provider(prompt):
                    provider_prompts.append(prompt)
                    return "answer"
                with patch("core.colony_panel._session_database_path", return_value=path):
                    render_colony_panel(ui, answer=provider)
                self.assertEqual(len(provider_prompts), expected_calls)
                self.assertEqual(
                    "cano_memory_benchmark" in ui.session_state, submit)
                if submit:
                    self.assertEqual(len(provider_prompts), 4)
                    self.assertTrue(all("Prefer primary evidence" not in prompt
                                        for prompt in provider_prompts[::2]))
                    self.assertTrue(all("Prefer primary evidence" in prompt
                                        for prompt in provider_prompts[1::2]))

    def test_ui_case_parser_bounds_and_normalizes_human_labeled_cases(self):
        cases = parse_memory_benchmark_cases(
            '[{"case_id":" case-1 ","prompt":" Question? ","expected":" Answer "}]')
        self.assertEqual(cases, (BenchmarkCase("case-1", "Question?", "Answer"),))
        for invalid in (
            "not json",
            '[]',
            '[{"case_id":"x","prompt":"p","expected":"e","unsafe":"x"}]',
            '[{"case_id":"x","prompt":"p"}]',
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_memory_benchmark_cases(invalid)

    def test_ui_case_parser_rejects_duplicate_ids_and_more_than_five_cases(self):
        duplicate = (
            '[{"case_id":"same","prompt":"p1","expected":"e"},'
            '{"case_id":"same","prompt":"p2","expected":"e"}]')
        with self.assertRaisesRegex(ValueError, "tekrarlanmamalı"):
            parse_memory_benchmark_cases(duplicate)
        too_many = [
            {"case_id": str(i), "prompt": f"p{i}", "expected": "e"}
            for i in range(6)
        ]
        with self.assertRaisesRegex(ValueError, "1 ile 5"):
            parse_memory_benchmark_cases(json.dumps(too_many))

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
