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


    def test_partial_model_response_is_counted_as_unscored(self):
        class PartialClient(BenchmarkClient):
            def verify(self, model, system, prompt):
                cases = json.loads(prompt.split("\\n", 1)[1])
                return json.dumps({"assessments": [
                    {"index": item["index"], "verdict": CASES[item["index"]]["expected"],
                     "reason": "fixture"}
                    for item in cases if item["index"] != 0
                ]})

        result = run_claim_review_benchmark(PartialClient())
        self.assertEqual(result["correct"], 11)
        self.assertEqual(result["confusion_matrix"]["supported"]["unscored"], 1)
        self.assertEqual(result["unscored"], 1)
        self.assertEqual(result["per_class"]["supported"]["support"], 4)
        self.assertEqual(result["per_class"]["supported"]["recall"], 0.75)
        self.assertEqual(
            sum(sum(row.values()) for row in result["confusion_matrix"].values()), 12)

    def test_empty_assessments_do_not_inflate_or_hide_denominators(self):
        class EmptyClient(BenchmarkClient):
            def verify(self, model, system, prompt):
                return json.dumps({"assessments": []})

        result = run_claim_review_benchmark(EmptyClient())
        self.assertEqual(result["correct"], 0)
        self.assertEqual(result["unscored"], 12)
        self.assertEqual(result["coverage"], 0)
        self.assertEqual(result["accuracy"], 0.0)
        for label in ("supported", "contradicted", "insufficient"):
            self.assertEqual(result["per_class"][label]["support"], 4)
            self.assertEqual(result["per_class"][label]["recall"], 0.0)
            self.assertEqual(result["confusion_matrix"][label]["unscored"], 4)


if __name__ == "__main__":
    unittest.main()

