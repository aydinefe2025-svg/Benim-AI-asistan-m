import json
import unittest

from core.claim_review_benchmark import (
    CASES, HUMAN_COMPARISON_CASES, load_expected_labels,
    run_claim_review_benchmark, score_labels,
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
        self.assertIn("single JSON object", prompt)
        self.assertIn('"assessments"', prompt)
        self.assertIn('integer "index"', prompt)
        self.assertEqual(result["total"], 12)
        self.assertEqual(result["correct"], 12)
        self.assertEqual(result["accuracy"], 1.0)
        self.assertEqual(result["confusion_matrix"]["supported"]["supported"], 4)
        self.assertIn("12 fixed synthetic", result["scope"])


    def test_v3_fixtures_are_source_linked_blind_and_interleaved(self):
        self.assertEqual(len(HUMAN_COMPARISON_CASES), 24)
        self.assertTrue(all("expected" not in case for case in HUMAN_COMPARISON_CASES))
        self.assertTrue(all(case.get("source_url", "").startswith("https://")
                            and case.get("source_title") for case in HUMAN_COMPARISON_CASES))
        self.assertEqual(len({case["source_url"] for case in HUMAN_COMPARISON_CASES}), 8)
        word_counts = {}
        case_counts = {}
        for case in HUMAN_COMPARISON_CASES:
            url = case["source_url"]
            word_counts[url] = word_counts.get(url, 0) + len(case["excerpt"].split())
            case_counts[url] = case_counts.get(url, 0) + 1
        self.assertTrue(all(count == 3 for count in case_counts.values()))
        self.assertTrue(all(count <= 25 for count in word_counts.values()))
        ids = [case["case_id"] for case in HUMAN_COMPARISON_CASES]
        self.assertEqual(ids, [f"v2_{index:02d}" for index in range(1, 25)])

    def test_v3_model_scoring_uses_external_gold_key_and_hides_it_from_prompt(self):
        with self.assertRaises(RuntimeError):
            run_claim_review_benchmark(BenchmarkClient(["supported"] * 24),
                                       cases=HUMAN_COMPARISON_CASES)
        answer_key = {case["case_id"]: "supported"
                      for case in HUMAN_COMPARISON_CASES}
        client = BenchmarkClient(["supported"] * 24)
        result = run_claim_review_benchmark(
            client, cases=HUMAN_COMPARISON_CASES, expected_labels=answer_key)
        self.assertEqual(result["total"], 24)
        self.assertEqual(result["correct"], 24)
        self.assertNotIn("expected", client.calls[0][2])

    def test_private_answer_key_parser_rejects_missing_or_wrong_keys(self):
        cases = ({"case_id": "a"}, {"case_id": "b"})
        with self.assertRaises(RuntimeError):
            load_expected_labels("", cases)
        with self.assertRaises(ValueError):
            load_expected_labels('{"a":"supported"}', cases)
        self.assertEqual(
            load_expected_labels(
                '{"a":"supported","b":"insufficient"}', cases),
            {"a": "supported", "b": "insufficient"})

    def test_human_scoring_requires_complete_valid_labels_and_reports_classes(self):
        cases = (
            {"case_id": "a", "expected": "supported"},
            {"case_id": "b", "expected": "contradicted"},
            {"case_id": "c", "expected": "insufficient"},
        )
        gold = {case["case_id"]: case["expected"] for case in cases}
        human = {"a": "supported", "b": "supported", "c": "insufficient"}
        scored = score_labels(cases, human, gold)
        self.assertEqual(scored["correct"], 2)
        self.assertEqual(scored["confusion_matrix"]["contradicted"]["supported"], 1)
        with self.assertRaises(ValueError):
            score_labels(cases, {}, gold)
        human["a"] = "unknown"
        with self.assertRaises(ValueError):
            score_labels(cases, human, gold)

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

