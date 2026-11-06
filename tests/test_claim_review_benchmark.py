import json
import unittest

from core.claim_review_benchmark import CASES, run_claim_review_benchmark


class BenchmarkClient:
    def __init__(self, verdicts=None):
        self.verdicts = verdicts or [case["expected"] for case in CASES]
        self.calls = []

    def verify(self, model, system, prompt):
        self.calls.append((model, system, prompt))
        cases = json.loads(prompt.split("\n", 1)[1])
        return json.dumps({"assessments": [
            {"index": item["index"], "verdict": self.verdicts[item["index"]],
             "reason": "Bounded benchmark fixture."}
            for item in cases
        ]})


class ClaimReviewBenchmarkTests(unittest.TestCase):
    def test_fixed_labels_are_hidden_and_perfect_confusion_matrix_is_reported(self):
        client = BenchmarkClient()
        result = run_claim_review_benchmark(client)
        self.assertEqual(len(client.calls), 1)
        model, _system, prompt = client.calls[0]
        self.assertEqual(model, "openai/gpt-oss-20b")
        self.assertNotIn("expected", prompt)
        self.assertEqual(result["total"], 12)
        self.assertEqual(result["correct"], 12)
        self.assertEqual(result["accuracy"], 1.0)
        self.assertEqual(result["confusion_matrix"]["supported"]["supported"], 4)
        self.assertIn("no human baseline", result["scope"])

    def test_wrong_verdict_is_counted_in_the_correct_confusion_cell(self):
        verdicts = [case["expected"] for case in CASES]
        verdicts[0] = "insufficient"
        result = run_claim_review_benchmark(BenchmarkClient(verdicts))
        self.assertEqual(result["correct"], 11)
        self.assertEqual(result["confusion_matrix"]["supported"]["insufficient"], 1)


if __name__ == "__main__":
    unittest.main()

