"""Validation tests for the structured scientific evidence profile."""
import unittest

from core.evidence_appraisal import validate_appraisal_profile


def profile(design="observational"):
    return {
        "study_design": design,
        "population": "Adults meeting the study inclusion criteria",
        "sample_size": "n=240 participants",
        "comparator": "Usual care",
        "outcome": "Prespecified symptom score at 12 weeks",
        "effect_estimate": "Mean difference -2.1 points",
        "uncertainty": "95% CI -3.5 to -0.7",
        "limitations": "Single-site study; short follow-up",
        "preregistration": "yes",
        "independent_replication": "unclear",
        "conflicting_evidence": "unclear",
    }


class EvidenceAppraisalValidationTests(unittest.TestCase):
    def test_keeps_dimensions_separate_and_preserves_uncertainty(self):
        got = validate_appraisal_profile(profile())
        self.assertEqual(got["effect_estimate"], "Mean difference -2.1 points")
        self.assertEqual(got["uncertainty"], "95% CI -3.5 to -0.7")
        self.assertEqual(got["independent_replication"], "unclear")
        self.assertNotIn("score", got)
        self.assertNotIn("claim_verified", got)

    def test_requires_explicit_unknowns_instead_of_silent_omissions(self):
        item = profile()
        item["limitations"] = ""
        with self.assertRaises(ValueError):
            validate_appraisal_profile(item)
        item = profile()
        item["preregistration"] = None
        with self.assertRaises(ValueError):
            validate_appraisal_profile(item)

    def test_randomized_trial_requires_result_level_rob2_notes(self):
        with self.assertRaises(ValueError):
            validate_appraisal_profile(profile("randomized_trial"))
        item = profile("randomized_trial")
        item["risk_of_bias"] = {
            domain: {"judgement": "unclear", "rationale": "The report does not say."}
            for domain in (
                "randomization", "deviations_from_interventions",
                "missing_outcome_data", "outcome_measurement", "selective_reporting",
            )
        }
        got = validate_appraisal_profile(item)
        self.assertEqual(len(got["risk_of_bias"]), 5)

    def test_refuses_to_apply_rob2_to_other_designs(self):
        item = profile()
        item["risk_of_bias"] = {}
        with self.assertRaises(ValueError):
            validate_appraisal_profile(item)

    def test_rejects_unrecognized_design_and_unbounded_text(self):
        item = profile()
        item["study_design"] = "high_quality"
        with self.assertRaises(ValueError):
            validate_appraisal_profile(item)
        item = profile()
        item["population"] = "x" * 1001
        with self.assertRaises(ValueError):
            validate_appraisal_profile(item)


if __name__ == "__main__":
    unittest.main()
