import json
import unittest

from core.claim_review_benchmark import (
    CASES, HUMAN_COMPARISON_CASES, run_claim_review_benchmark, score_labels,
)


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
        model, system, prompt = client.calls[0]
        self.assertEqual(model, "openai/gpt-oss-120b")
        self.assertIn("Merely reporting adults", system)
        self.assertNotIn("expected", prompt)
        self.assertEqual(result["total"], 12)
        self.assertEqual(result["correct"], 12)
        self.assertEqual(result["accuracy"], 1.0)
        self.assertEqual(result["confusion_matrix"]["supported"]["supported"], 4)
        self.assertIn("12 fixed synthetic", result["scope"])


    def test_v2_is_new_balanced_set_and_hidden_from_model_prompt(self):
        self.assertEqual(len(HUMAN_COMPARISON_CASES), 24)
        self.assertTrue(set(c["case_id"] for c in CASES).isdisjoint(
            c["case_id"] for c in HUMAN_COMPARISON_CASES))
        self.assertEqual(
            {label: sum(c["expected"] == label for c in HUMAN_COMPARISON_CASES)
             for label in ("supported", "contradicted", "insufficient")},
            {"supported": 8, "contradicted": 8, "insufficient": 8})
        client = BenchmarkClient([c["expected"] for c in HUMAN_COMPARISON_CASES])
        result = run_claim_review_benchmark(client, cases=HUMAN_COMPARISON_CASES)
        self.assertEqual(result["total"], 24)
        self.assertEqual(result["correct"], 24)
        self.assertNotIn("expected", client.calls[0][2])

    def test_human_scoring_requires_complete_valid_labels(self):
        labels = {c["case_id"]: c["expected"] for c in HUMAN_COMPARISON_CASES}
        self.assertEqual(score_labels(HUMAN_COMPARISON_CASES, labels)["correct"], 24)
        with self.assertRaises(ValueError):
            score_labels(HUMAN_COMPARISON_CASES, {})
        labels[next(iter(labels))] = "unknown"
        with self.assertRaises(ValueError):
            score_labels(HUMAN_COMPARISON_CASES, labels)

    def test_wrong_verdict_is_counted_in_the_correct_confusion_cell(self):
        verdicts = [case["expected"] for case in CASES]
        verdicts[0] = "insufficient"
        result = run_claim_review_benchmark(BenchmarkClient(verdicts))
        self.assertEqual(result["correct"], 11)
        self.assertEqual(result["confusion_matrix"]["supported"]["insufficient"], 1)


    def test_partial_model_response_is_counted_as_unscored(self):
        class PartialClient(BenchmarkClient):
            def verify(self, model, system, prompt):
                cases = json.loads(prompt.split("\n", 1)[1])
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

