import unittest

from scripts.cano_continuation_gate import is_eligible


def valid_report():
    roles = [
        {"role": name, "status": "passed",
         "execution": "isolated_read_only_subprocess", "model_calls": 0}
        for name in ("evidence", "generation", "continuity", "security")
    ]
    return {
        "github_run_id": "12345",
        "db_integrity": "ok",
        "specialist_agents": {"status": "passed", "roles": roles},
        "virtual_generation": {
            "lesson_status": "transferred",
            "training": {"positive_evidence": True},
            "held_out_confirmation": {"positive_evidence": True},
        },
    }


class CanoContinuationGateTests(unittest.TestCase):
    def test_all_validations_and_both_positive_evaluations_allow_followup(self):
        self.assertTrue(is_eligible(valid_report(), "12345"))

    def test_rejected_lesson_stops_followup(self):
        report = valid_report()
        report["virtual_generation"]["lesson_status"] = "rejected"
        self.assertFalse(is_eligible(report, "12345"))

    def test_nonpositive_training_evaluation_stops_followup(self):
        report = valid_report()
        report["virtual_generation"]["training"]["positive_evidence"] = False
        self.assertFalse(is_eligible(report, "12345"))

    def test_nonpositive_heldout_evaluation_stops_followup(self):
        report = valid_report()
        report["virtual_generation"]["held_out_confirmation"]["positive_evidence"] = False
        self.assertFalse(is_eligible(report, "12345"))

    def test_run_id_must_match_source_run(self):
        self.assertFalse(is_eligible(valid_report(), "other"))

    def test_database_integrity_must_pass(self):
        report = valid_report()
        report["db_integrity"] = "corrupt"
        self.assertFalse(is_eligible(report, "12345"))

    def test_all_four_isolated_zero_call_reviewers_must_pass(self):
        report = valid_report()
        report["specialist_agents"]["roles"][0]["model_calls"] = 1
        self.assertFalse(is_eligible(report, "12345"))

    def test_malformed_report_is_rejected(self):
        self.assertFalse(is_eligible([], "12345"))
        self.assertFalse(is_eligible({}, "12345"))


if __name__ == "__main__":
    unittest.main()
