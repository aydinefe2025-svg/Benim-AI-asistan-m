"""Deterministic local benchmarks with stable suite identity.

No network, automatic model provisioning, or deployment. A caller supplies
a local responder; two equal passes only prove repeatability in those passes.
"""
import unittest

from core.benchmark_harness import (BenchmarkCase, benchmark_sha256, run_benchmark, run_paired_benchmark)
from core.agent_evolution import AgentEvaluator


class BenchmarkHarnessTests(unittest.TestCase):
    def setUp(self):
        self.cases = (
            BenchmarkCase("A", "2 + 2?", "4"),
            BenchmarkCase("B", "Turkish for hello?", "merhaba"),
        )

    def test_identical_cases_have_stable_hash_across_input_order(self):
        self.assertEqual(benchmark_sha256(self.cases),
                         benchmark_sha256(tuple(reversed(self.cases))))
        self.assertEqual(len(benchmark_sha256(self.cases)), 64)
        changed = (BenchmarkCase("A", "2 + 2?", "5"), self.cases[1])
        self.assertNotEqual(benchmark_sha256(self.cases),
                            benchmark_sha256(changed))

    def test_run_twice_returns_measured_candidate_with_matched_suite(self):
        calls = []
        def responder(prompt):
            calls.append(prompt)
            return {"2 + 2?": "4", "Turkish for hello?": "merhaba"}[prompt]
        result = run_benchmark("candidate", self.cases, responder,
                               source_refs=("local:test-evidence",),
                               safety_pass=True)
        self.assertEqual(result.passed, 2)
        self.assertEqual(result.total, 2)
        self.assertTrue(result.reproducible)
        self.assertEqual(result.benchmark_sha256, benchmark_sha256(self.cases))
        self.assertEqual(len(calls), 4)

    def test_nondeterministic_candidate_is_not_reproducible(self):
        calls = []
        def responder(prompt):
            calls.append(prompt)
            return "4" if len(calls) == 1 else "wrong"
        result = run_benchmark("nondeterministic", (self.cases[0],), responder,
                               source_refs=("local",), safety_pass=True)
        self.assertEqual(result.passed, 1)
        self.assertFalse(result.reproducible)

    def test_measured_baseline_and_candidate_produce_proposal_not_auto_upgrade(self):
        def baseline(prompt):
            return "4" if prompt == "2 + 2?" else "wrong"
        def improved(prompt):
            return "4" if prompt == "2 + 2?" else "merhaba"
        old = run_benchmark("stable", self.cases, baseline,
                            source_refs=("unit:baseline",), safety_pass=True)
        new = run_benchmark("candidate", self.cases, improved,
                            source_refs=("unit:candidate",), safety_pass=True)
        gate = AgentEvaluator(baseline=old, min_tests=2)
        decision = gate.evaluate(new)
        self.assertEqual(decision["status"], "proposal")
        self.assertEqual(decision["delta"], 0.5)
        self.assertEqual(gate.active.name, "stable")
        self.assertEqual(gate.audit_log[-1]["benchmark_sha256"],
                         benchmark_sha256(self.cases))

    def test_duplicate_case_ids_and_bad_dataset_rejected_before_running(self):
        calls = []
        with self.assertRaises(ValueError):
            run_benchmark("x", (self.cases[0], self.cases[0]),
                          lambda prompt: calls.append(prompt),
                          source_refs=("e",), safety_pass=True)
        with self.assertRaises(ValueError):
            benchmark_sha256(())
        self.assertEqual(calls, [])

    def test_raised_responder_error_is_recorded_as_failure_not_fake_success(self):
        result = run_benchmark("broken", (self.cases[0],),
                               lambda prompt: (_ for _ in ()).throw(RuntimeError("offline")),
                               source_refs=("e",), safety_pass=True)
        self.assertEqual(result.passed, 0)
        self.assertFalse(result.reproducible)


    def test_paired_memory_candidate_reports_per_task_improvements_and_regressions(self):
        cases = (
            BenchmarkCase("A", "prompt-a", "right-a"),
            BenchmarkCase("B", "prompt-b", "right-b"),
            BenchmarkCase("C", "prompt-c", "right-c"),
        )
        baseline_calls = []
        candidate_calls = []
        baseline_outputs = {"prompt-a": "right-a", "prompt-b": "wrong", "prompt-c": "right-c"}
        candidate_outputs = {"prompt-a": "right-a", "prompt-b": "right-b", "prompt-c": "wrong"}
        result = run_paired_benchmark(
            "no-memory", "memory-enabled", cases,
            lambda prompt: baseline_calls.append(prompt) or baseline_outputs[prompt],
            lambda prompt: candidate_calls.append(prompt) or candidate_outputs[prompt],
            source_refs=("fixture:memory-learning-v1",), safety_pass=True,
        )
        self.assertEqual(result["baseline"].passed, 2)
        self.assertEqual(result["candidate"].passed, 2)
        self.assertEqual(result["delta"], 0.0)
        self.assertEqual(result["improved_case_ids"], ["B"])
        self.assertEqual(result["regressed_case_ids"], ["C"])
        self.assertEqual([item["outcome"] for item in result["case_results"]],
                         ["unchanged", "improved", "regressed"])
        self.assertEqual(result["reproducible"], {"baseline": True, "candidate": True})
        self.assertEqual(len(baseline_calls), 6)
        self.assertEqual(len(candidate_calls), 6)
        self.assertNotIn("right-a", repr(result))
        self.assertEqual(result["baseline"].benchmark_sha256,
                         result["candidate"].benchmark_sha256)

    def test_paired_benchmark_treats_failures_as_regressions_without_leaking_errors(self):
        case = (BenchmarkCase("private-case-id", "sensitive prompt", "expected"),)
        result = run_paired_benchmark(
            "no-memory", "memory-enabled", case,
            lambda _: "expected",
            lambda _: (_ for _ in ()).throw(RuntimeError("secret provider token")),
            source_refs=("fixture:failure",), safety_pass=True,
        )
        self.assertEqual(result["regressed_case_ids"], ["private-case-id"])
        self.assertFalse(result["reproducible"]["candidate"])
        self.assertNotIn("secret provider token", repr(result))
        self.assertNotIn("sensitive prompt", repr(result))

    def test_paired_benchmark_validates_before_any_responder_runs(self):
        calls = []
        with self.assertRaises(ValueError):
            run_paired_benchmark(
                "baseline", "candidate", (), lambda _: calls.append("b"),
                lambda _: calls.append("c"), source_refs=("fixture",), safety_pass=True,
            )
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
