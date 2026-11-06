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
        item["risk_of_bias"] = {"randomization": "low"}
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


class _DraftModel:
    def chat(self, model, system, prompt):
        return "Unverified research draft."


class _QuoteModel:
    def chat(self, model, system, prompt):
        import json
        return json.dumps({"claims": [{
            "claim": "Example research finding",
            "doi": "10.1038/nprot.2013.143",
            "quote": "Targeted nucleases are powerful tools for genome engineering.",
        }]})


class EvidenceAppraisalPersistenceTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from core.agent_colony import AgentColony
        from core.collaborative_mission import CollaborativeMission
        from core.claim_evidence import audit_claim_quotes
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        colony = AgentColony(Path(self.tmp.name) / "colony.sqlite3")
        colony.create_founder("research", "Research")
        colony.grow_specialists(approved=True)
        self.manager = CollaborativeMission(colony)
        record = self.manager.execute(
            "Read paper DOI 10.1038/nprot.2013.143",
            client=_DraftModel(), model="stub",
            source_lookup=lambda q, limit=3: [{
                "title": "Genome engineering",
                "url": "https://doi.org/10.1038/nprot.2013.143",
            }])
        self.mission_id = record["id"]
        self.manager.inspect_source_documents(
            self.mission_id,
            reader=lambda doi: {
                "doi": doi, "status": "full_text_excerpt",
                "title": "Genome engineering",
                "url": "https://europepmc.org/articles/PMC1234567",
                "excerpt": "Targeted nucleases are powerful tools for genome engineering. Results follow.",
                "claim_verified": False,
            })
        audit_claim_quotes(self.manager, self.mission_id,
                           client=_QuoteModel(), model="stub")

    def test_appraisal_is_authenticated_audited_and_does_not_verify_claim(self):
        from core.evidence_appraisal import record_claim_evidence_appraisal
        with self.assertRaises(PermissionError):
            record_claim_evidence_appraisal(
                self.manager, self.mission_id, 0,
                reviewer_id="unverified", profile=profile())
        result = record_claim_evidence_appraisal(
            self.manager, self.mission_id, 0,
            reviewer_id="oidc_" + "a" * 64, profile=profile())
        self.assertEqual(result["profile"]["study_design"], "observational")
        self.assertEqual(len(result["evidence_digest"]), 64)
        self.assertEqual(result["interpretation"],
                         "structured_human_appraisal_no_universal_score")
        saved = self.manager.get(self.mission_id)
        claim = saved["stages"][0]["source_claim_audit"][0]
        self.assertFalse(claim["claim_verified"])
        self.assertEqual(len(claim["evidence_appraisal_events"]), 1)
        self.assertEqual(saved["status"], "review_pending")


if __name__ == "__main__":
    unittest.main()
