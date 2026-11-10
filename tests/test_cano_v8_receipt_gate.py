"""Synthetic, offline contract tests. Not V8 adversarial test results."""
import copy
import hashlib
import unittest

from scripts.cano_v8_receipt_gate import audit_receipt


class V8ReceiptAuditTests(unittest.TestCase):
    def build(self):
        def sample(prefix, i, decision):
            name = f"{prefix}-{i:02d}"
            return {"case_id": name, "sha256": hashlib.sha256(name.encode()).hexdigest(),
                    "decision": decision, "artifact_sample_ref": f"results/{name}.json"}
        attack = [sample("A", i, "blocked") for i in range(34)]
        attack[31]["decision"] = "allowed"
        attack[32]["decision"] = "undetermined"
        attack[33]["decision"] = "error"
        benign = [sample("B", i, "allowed") for i in range(5)]
        benign[3]["decision"] = "blocked"
        benign[4]["decision"] = "undetermined"
        return {
            "schema_version": 1,
            "suite_id": "CANO-V8-34",
            "provenance": {"repo": "example/CANO", "commit_sha": "a" * 40,
                           "ci_run_id": 12345, "suite_sha256": "b" * 64,
                           "artifact_sha256": "c" * 64,
                           "artifact_url": "https://github.com/example/CANO/actions/runs/12345/artifacts"},
            "attack_samples": attack,
            "benign_holdout": {"source_url": "https://example.org/benign-dataset",
                               "license": "CC-BY-4.0", "samples": benign},
        }

    def test_missing_manifest_cannot_be_success_or_zero_failure(self):
        result = audit_receipt({})
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["metrics"])
        self.assertFalse(result["evidence_verified"])

    def test_34_attacks_without_benign_holdout_do_not_claim_fp_zero(self):
        manifest = self.build()
        manifest.pop("benign_holdout")
        result = audit_receipt(manifest)
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["metrics"])

    def test_missing_one_attack_is_not_34_case_coverage(self):
        manifest = self.build()
        manifest["attack_samples"].pop()
        self.assertEqual(audit_receipt(manifest)["status"], "blocked")

    def test_duplicated_case_id_is_rejected(self):
        manifest = self.build()
        manifest["attack_samples"][1]["case_id"] = manifest["attack_samples"][0]["case_id"]
        self.assertEqual(audit_receipt(manifest)["status"], "blocked")

    def test_missing_ci_and_artifact_provenance_is_rejected(self):
        manifest = self.build()
        manifest["provenance"]["artifact_sha256"] = ""
        manifest["provenance"]["ci_run_id"] = 0
        self.assertEqual(audit_receipt(manifest)["status"], "blocked")
        self.assertIsNone(audit_receipt(manifest)["metrics"])

    def test_external_host_cannot_impersonate_github_artifact(self):
        manifest = self.build()
        manifest["provenance"]["artifact_url"] = (
            "https://evil.example/actions/runs/12345/artifacts"
        )
        result = audit_receipt(manifest)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("missing_artifact_reference", result["errors"])
        self.assertIsNone(result["metrics"])

    def test_wrong_repository_or_run_artifact_url_is_rejected(self):
        urls = (
            "https://github.com/attacker/CANO/actions/runs/12345/artifacts",
            "https://github.com/example/CANO/actions/runs/99999/artifacts",
            "https://github.com.evil.example/example/CANO/actions/runs/12345/artifacts",
        )
        for url in urls:
            with self.subTest(url=url):
                manifest = self.build()
                manifest["provenance"]["artifact_url"] = url
                result = audit_receipt(manifest)
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["metrics"])

    def test_false_positive_false_negative_unknown_and_errors_are_separate(self):
        result = audit_receipt(self.build())
        self.assertEqual(result["status"], "metadata_ready_unverified")
        self.assertEqual(result["metrics"]["TP"], 31)
        self.assertEqual(result["metrics"]["FN"], 1)
        self.assertEqual(result["metrics"]["TN"], 3)
        self.assertEqual(result["metrics"]["FP"], 1)
        self.assertEqual(result["metrics"]["U"], 2)
        self.assertEqual(result["metrics"]["ERR"], 1)
        self.assertEqual(result["metrics"]["total"], 39)
        self.assertEqual(result["metrics"]["evaluated"], 36)
        self.assertAlmostEqual(result["metrics"]["coverage"], 36 / 39)
        self.assertAlmostEqual(result["metrics"]["false_positive_rate"], 1 / 4)
        self.assertAlmostEqual(result["metrics"]["false_negative_rate"], 1 / 32)
        self.assertFalse(result["evidence_verified"])

    def test_bad_outcome_or_missing_sample_hash_fails_closed(self):
        manifest = self.build()
        manifest["attack_samples"][0]["decision"] = "success"
        manifest["attack_samples"][1]["sha256"] = ""
        self.assertEqual(audit_receipt(manifest)["status"], "blocked")

    def test_no_sample_reference_fails_closed(self):
        manifest = self.build()
        manifest["attack_samples"][0]["artifact_sample_ref"] = ""
        self.assertEqual(audit_receipt(manifest)["status"], "blocked")

    def test_nonstring_decision_fails_closed_without_crashing(self):
        manifest = self.build()
        manifest["attack_samples"][0]["decision"] = []
        result = audit_receipt(manifest)
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["metrics"])

    def test_unclassified_benign_does_not_count_as_zero_false_positives(self):
        manifest = self.build()
        for item in manifest["benign_holdout"]["samples"]:
            item["decision"] = "undetermined"
        result = audit_receipt(manifest)
        self.assertEqual(result["status"], "metadata_ready_unverified")
        self.assertIsNone(result["metrics"]["false_positive_rate"])
        self.assertFalse(result["independent_holdout_verified"])

    def test_a_valid_structure_is_never_claimed_verified(self):
        result = audit_receipt(self.build())
        self.assertFalse(result["evidence_verified"])
        self.assertNotEqual(result["status"], "verified")


if __name__ == "__main__":
    unittest.main()
