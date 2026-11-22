import unittest
from core.lora_candidate_gate import candidate_gate

HASH = "a" * 64
SAFETY_IDS = ["secret_handling", "tool_completion_claim", "training_requires_review", "paid_api_approval", "preserve_prior_adapter", "honest_scope"]

def evaluation(name, passed, ids):
    return {
        "dataset_sha256": HASH,
        "rubric": "same checks",
        "scoring_scope": "raw model outputs",
        "generation_config": {"temperature": 0, "max_new_tokens": 128},
        "training_data_integrity": {"status": "verified", "verified": True, "sha256": "b" * 64},
        "training_overlap_audit": {"status": "no_lexical_overlap_detected", "has_overlap": False},
        "results": [{"name": name, "cases": [{"id": case_id, "passed": index < passed, "missing_checks": [] if index < passed else ["required check"], "rejected_terms": []} for index, case_id in enumerate(ids)]}],
    }

class CandidateGateTests(unittest.TestCase):
    def test_only_qualifies_for_human_review_and_never_activates(self):
        result = candidate_gate(evaluation("baseline", 2, ["a", "b", "c", "d"]), evaluation("candidate", 3, ["a", "b", "c", "d"]), evaluation("safety", 6, SAFETY_IDS))
        self.assertEqual(result["decision"], "eligible_for_human_review")
        self.assertFalse(result["automatic_activation"])

    def test_missing_integrity_or_clean_holdout_evidence_rejects(self):
        candidate = evaluation("candidate", 4, ["a", "b", "c", "d"])
        candidate.pop("training_overlap_audit")
        result = candidate_gate(evaluation("baseline", 2, ["a", "b", "c", "d"]), candidate, evaluation("safety", 6, SAFETY_IDS))
        self.assertIn("candidate_holdout_overlap_unverified", result["reasons"])

    def test_incomplete_safety_coverage_rejects(self):
        result = candidate_gate(evaluation("baseline", 2, ["a", "b", "c", "d"]), evaluation("candidate", 4, ["a", "b", "c", "d"]), evaluation("safety", 2, SAFETY_IDS[:2]))
        self.assertIn("safety_suite_missing_required_cases", result["reasons"])

    def test_generation_settings_must_match(self):
        candidate = evaluation("candidate", 4, ["a", "b", "c", "d"])
        candidate["generation_config"]["max_new_tokens"] = 256
        result = candidate_gate(evaluation("baseline", 2, ["a", "b", "c", "d"]), candidate, evaluation("safety", 6, SAFETY_IDS))
        self.assertIn("baseline_and_candidate_generation_config_mismatch", result["reasons"])

    def test_no_score_gain_rejects(self):
        result = candidate_gate(evaluation("baseline", 3, ["a", "b", "c", "d"]), evaluation("candidate", 3, ["a", "b", "c", "d"]), evaluation("safety", 6, SAFETY_IDS))
        self.assertIn("candidate_did_not_strictly_improve_baseline", result["reasons"])

if __name__ == "__main__":
    unittest.main()
