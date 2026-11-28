"""Fast, standard-library regression tests for public J0740 evidence gates."""
import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research/j0740/windows_access/verify_nuisance_evidence_gates.py"
REPORT = ROOT / "research/j0740/nuisance_proposal_regression_and_k4_comparison_2026-11-11.json"
spec = importlib.util.spec_from_file_location("j0740_public_gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class PublicSummaryGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads(REPORT.read_text(encoding="utf-8"))

    def snapshot(self):
        return copy.deepcopy(self.reference)

    def test_real_archived_summary_matches_predeclared_decisions(self):
        result = gate.verify_report(self.snapshot())
        self.assertEqual([p["status"] for p in result["points"]],
                         ["PASS", "FAIL", "FAIL", "PASS"])
        self.assertEqual(result["public_summary_arithmetic"], "PASS")
        self.assertEqual(result["private_photon_npz_independent_check"], "NOT_PERFORMED")
        self.assertEqual(result["k4_k8_paired_superiority"], "NOT_ESTABLISHED")
        self.assertEqual(result["full_MR_domain_convergence"], "NOT_ESTABLISHED")
        self.assertEqual(result["EOS_Bayes"], "NOT_RUN")
        self.assertEqual(result["points"][1]["gates"]["ESS"], False)
        self.assertEqual(result["points"][1]["gates"]["budget_drift"], False)
        self.assertEqual(result["points"][2]["gates"]["max_weight"], False)
        self.assertTrue(all(result["points"][3]["gates"].values()))

    def test_cli_runs_without_numpy_scipy_or_private_data(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), str(REPORT)],
                              text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(len(result["points"]), 4)
        self.assertEqual(result["EOS_Bayes"], "NOT_RUN")

    def test_false_success_label_rejected(self):
        doc = self.snapshot()
        doc["v2_heldout_results"]["status"] = "PASS"
        with self.assertRaises(gate.EvidenceError):
            gate.verify_report(doc)

    def test_hidden_weight_failure_rejected(self):
        doc = self.snapshot()
        doc["v3_heldout_results"]["max_weight"][0] = 0.25
        with self.assertRaises(gate.EvidenceError):
            gate.verify_report(doc)

    def test_nonfinite_metrics_rejected(self):
        doc = self.snapshot()
        doc["v1_heldout_results"]["point_2_073_13_25"]["ESS"][1] = float("nan")
        with self.assertRaises(gate.EvidenceError):
            gate.verify_report(doc)

    def test_raised_acceptance_threshold_rejected(self):
        doc = self.snapshot()
        doc["new_method"]["thresholds_unchanged"]["max_weight_fraction_max"] = 0.20
        with self.assertRaises(gate.EvidenceError):
            gate.verify_report(doc)

    def test_training_point_reuse_rejected(self):
        doc = self.snapshot()
        doc["v3_heldout_results"]["heldout_point_msun_km"] = [2.0, 14.0]
        with self.assertRaises(gate.EvidenceError):
            gate.verify_report(doc)

    def test_training_seed_reuse_rejected(self):
        doc = self.snapshot()
        doc["v3_heldout_results"]["seeds"][0] = doc["v3_heldout_results"]["training_seeds"][0]
        with self.assertRaises(gate.EvidenceError):
            gate.verify_report(doc)

    def test_missing_model_digest_rejected(self):
        doc = self.snapshot()
        doc["v3_heldout_results"]["model_sha256"] = "00" * 32
        with self.assertRaises(gate.EvidenceError):
            gate.verify_report(doc)

    def test_modified_likelihood_rejected(self):
        doc = self.snapshot()
        doc["k4_experiments_are_distinct"]["shared_physics"]["source_prior_or_likelihood_changed"] = True
        with self.assertRaises(gate.EvidenceError):
            gate.verify_report(doc)

    def test_eos_bayes_cannot_be_promoted_by_summary(self):
        doc = self.snapshot()
        doc["EOS_Bayes"] = "PASS"
        with self.assertRaises(gate.EvidenceError):
            gate.verify_report(doc)

    def test_history_cannot_hide_low_ess_seed(self):
        doc = self.snapshot()
        doc["k2_15_26_ess_correction"]["range"] = [99.62165806980663, 133.887395]
        with self.assertRaises(gate.EvidenceError):
            gate.verify_report(doc)


if __name__ == "__main__":
    unittest.main()
