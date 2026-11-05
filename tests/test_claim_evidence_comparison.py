import unittest

from core.claim_evidence_comparison import compare_claim_to_sources


class ClaimEvidenceComparisonTests(unittest.TestCase):
    def compare_one(self, claim, text):
        return compare_claim_to_sources(claim, [{
            "title": "Fixture source", "url": "https://example.org/paper", "content": text,
        }])

    def test_finds_a_passage_and_returns_a_verifiable_citation(self):
        result = self.compare_one(
            "The treatment reduces fever",
            "A different cohort was observed. The treatment reduces fever in adults.",
        )
        self.assertEqual(result["assessment"], "possible_support")
        match = result["passages"][0]
        self.assertIn("treatment reduces fever", match["passage"])
        self.assertEqual(match["citation"]["url"], "https://example.org/paper")
        self.assertEqual(len(match["citation"]["compared_text_sha256"]), 64)
        self.assertFalse(result["independently_verified"])

    def test_explicit_negation_is_reported_as_a_possible_contradiction(self):
        result = self.compare_one(
            "The treatment reduces fever",
            "The treatment does not reduce fever in adults.",
        )
        self.assertEqual(result["assessment"], "possible_contradiction")

    def test_turkish_explicit_negation_is_reported(self):
        result = self.compare_one(
            "Bu yöntem hücre büyümesini artırır",
            "Bu yöntem hücre büyümesini artırmaz.",
        )
        self.assertEqual(result["assessment"], "possible_contradiction")

    def test_unrelated_text_is_not_misreported_as_support(self):
        result = self.compare_one("The treatment reduces fever", "The sky is clear today.")
        self.assertEqual(result["assessment"], "insufficient_text_match")
        self.assertEqual(result["passages"], [])

    def test_only_provided_text_is_examined_and_status_never_changes(self):
        result = compare_claim_to_sources("Claim about evidence", [])
        self.assertEqual(result["sources_examined"], 0)
        self.assertFalse(result["claim_status_changed"])
        self.assertEqual(result["assessment"], "insufficient_text_match")

    def test_rejects_invalid_sources_and_unbounded_inputs(self):
        with self.assertRaises(ValueError):
            compare_claim_to_sources("Useful claim", [{
                "title": "bad", "url": "file:///secret", "content": "Useful evidence",
            }])
        with self.assertRaises(ValueError):
            compare_claim_to_sources("Useful claim", [{
                "title": "too long", "url": "https://example.org",
                "content": "x" * 200_001,
            }])

    def test_synthetic_precision_recall_benchmark_is_explicitly_bounded(self):
        # Eight hand-labeled fixtures benchmark passage triage only; they are
        # not a scientific corpus and do not calibrate real-world accuracy.
        cases = [
            ("The drug reduces pain", "The drug reduces pain in adults.", "possible_support"),
            ("Method improves yield", "Method improves yield by ten percent.", "possible_support"),
            ("Cells produce protein", "Cells produce protein under these conditions.", "possible_support"),
            ("The model predicts rainfall", "The model predicts rainfall tomorrow.", "possible_support"),
            ("The drug reduces pain", "The drug does not reduce pain in adults.", "possible_contradiction"),
            ("Method improves yield", "Method does not improve yield.", "possible_contradiction"),
            ("Cells produce protein", "Cells did not produce protein.", "possible_contradiction"),
            ("The model predicts rainfall", "The model never predicts rainfall.", "possible_contradiction"),
        ]
        tp = fp = fn = 0
        for claim, text, expected in cases:
            actual = self.compare_one(claim, text)["assessment"]
            predicted_positive = actual == "possible_support"
            expected_positive = expected == "possible_support"
            tp += predicted_positive and expected_positive
            fp += predicted_positive and not expected_positive
            fn += not predicted_positive and expected_positive
            self.assertEqual(actual, expected)
        self.assertEqual(tp / (tp + fp), 1.0)
        self.assertEqual(tp / (tp + fn), 1.0)


if __name__ == "__main__":
    unittest.main()

