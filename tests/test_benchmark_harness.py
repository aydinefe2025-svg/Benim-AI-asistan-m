"""Deterministic local benchmarks with stable suite identity.

No network, automatic model provisioning, or deployment. A caller supplies
a local responder; two equal passes only prove repeatability in those passes.
"""
import unittest

from core.benchmark_harness import BenchmarkCase, benchmark_sha256, run_benchmark


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


if __name__ == "__main__":
    unittest.main()
