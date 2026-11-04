"""Bounded specialist mission execution tests.

Uses a fake local LLM, so this proves orchestration mechanics, not that
independent external agents or real-world experiments have run.
"""
import unittest

from core.specialist_mission import SpecialistMission


class FakeLLM:
    def __init__(self):
        self.calls = []

    def chat(self, model, system, prompt, *, temperature=0.2):
        self.calls.append({"model": model, "system": system, "prompt": prompt})
        return f"output-{len(self.calls)}"


class SpecialistMissionTests(unittest.TestCase):
    def test_six_roles_execute_in_safe_sequence(self):
        llm = FakeLLM()
        runner = SpecialistMission(llm)
        result = runner.run(
            "Assess a virtual robot controller before any hardware test",
            model="qwen3:8b", domain="robotics_simulation",
        )
        self.assertEqual(result["status"], "draft_unverified")
        self.assertEqual(result["independent_verification"], False)
        self.assertEqual(len(llm.calls), 6)
        self.assertEqual([item["role"] for item in result["steps"]], [
            "planner", "discovery", "engineer", "skeptic", "replicator", "archivist",
        ])
        self.assertEqual(result["execution_environment"], "llm_only")
        self.assertTrue(all(item["output"] for item in result["steps"]))
        self.assertIn("output-4", llm.calls[4]["prompt"])
        self.assertIn("output-5", llm.calls[5]["prompt"])

    def test_cell_computational_mission_explicitly_excludes_laboratory_operations(self):
        llm = FakeLLM()
        result = SpecialistMission(llm).run(
            "Explore cell-inspired materials", model="qwen3:8b",
            domain="computational_cell_model",
        )
        self.assertEqual(result["status"], "draft_unverified")
        self.assertTrue(all("not perform laboratory experiments" in call["system"]
                            for call in llm.calls))
        self.assertFalse(result["real_cells_created"])

    def test_unknown_domain_and_empty_question_rejected_before_model_calls(self):
        llm = FakeLLM()
        runner = SpecialistMission(llm)
        with self.assertRaises(ValueError):
            runner.run("Task", model="qwen3:8b", domain="unrestricted_lab")
        with self.assertRaises(ValueError):
            runner.run("   ", model="qwen3:8b", domain="robotics_simulation")
        self.assertEqual(llm.calls, [])

    def test_failed_agent_does_not_claim_success_or_archive(self):
        class InterruptedLLM(FakeLLM):
            def chat(self, model, system, prompt, *, temperature=0.2):
                if len(self.calls) == 3:
                    raise RuntimeError("model unavailable")
                return super().chat(model, system, prompt, temperature=temperature)
        llm = InterruptedLLM()
        with self.assertRaisesRegex(RuntimeError, "model unavailable"):
            SpecialistMission(llm).run("Virtual test", model="qwen3:8b",
                                       domain="robotics_simulation")
        self.assertEqual(len(llm.calls), 3)


if __name__ == "__main__":
    unittest.main()
