import json
import unittest
from core.benchmark_harness import (
    BenchmarkCase, parse_memory_benchmark_cases, run_paired_benchmark,
)

class BenchmarkDistinctCaseTests(unittest.TestCase):
    def test_relabelled_identical_questions_cannot_inflate_gain(self):
        calls = []
        cases = tuple(BenchmarkCase(str(i), "Same question?", "yes") for i in range(5))
        with self.assertRaisesRegex(ValueError, "Duplicate benchmark prompts"):
            run_paired_benchmark("old", "new", cases,
                lambda _: calls.append("old") or "no",
                lambda _: calls.append("new") or "yes",
                source_refs=("fixture",), safety_pass=False)
        self.assertEqual(calls, [])

    def test_whitespace_duplicate_with_conflicting_expected_answer_is_rejected(self):
        raw = json.dumps([
            {"case_id": "a", "prompt": "Check evidence.", "expected": "yes"},
            {"case_id": "b", "prompt": " Check  evidence. ", "expected": "no"},
        ])
        with self.assertRaisesRegex(ValueError, "Duplicate benchmark prompts"):
            parse_memory_benchmark_cases(raw)

    def test_distinct_prompts_can_share_expected_answer(self):
        cases = (BenchmarkCase("a", "Verify a file.", "yes"),
                 BenchmarkCase("b", "Verify a result.", "yes"))
        result = run_paired_benchmark("old", "new", cases,
            lambda _: "no", lambda _: "yes",
            source_refs=("fixture",), safety_pass=False)
        self.assertEqual(result["candidate"].passed, 2)
        self.assertEqual(result["baseline"].passed, 0)
