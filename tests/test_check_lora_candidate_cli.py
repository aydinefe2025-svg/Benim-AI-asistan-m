import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SAFETY_IDS = [
    "secret_handling", "tool_completion_claim", "training_requires_review",
    "paid_api_approval", "preserve_prior_adapter", "honest_scope",
]


def evaluation(name, passed, case_ids):
    return {
        "dataset_sha256": "a" * 64,
        "rubric": "same checks",
        "scoring_scope": "raw model outputs",
        "generation_config": {"temperature": 0, "max_new_tokens": 128},
        "training_data_integrity": {
            "status": "verified", "verified": True, "sha256": "b" * 64,
        },
        "training_overlap_audit": {
            "status": "no_lexical_overlap_detected", "has_overlap": False,
        },
        "results": [{
            "name": name,
            "cases": [{
                "id": case_id,
                "passed": index < passed,
                "missing_checks": [] if index < passed else ["required check"],
                "rejected_terms": [],
            } for index, case_id in enumerate(case_ids)],
        }],
    }


class CheckLoraCandidateCliTests(unittest.TestCase):
    def run_cli(self, folder, payloads):
        paths = []
        for name, payload in payloads.items():
            path = folder / f"{name}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            paths.append(path)
        root = Path(__file__).resolve().parents[1]
        command = [
            sys.executable, str(root / "tools" / "check_lora_candidate.py"),
            "--baseline", str(paths[0]), "--candidate", str(paths[1]),
            "--safety", str(paths[2]),
        ]
        return subprocess.run(
            command, cwd=root, capture_output=True, text=True,
            timeout=10, check=False,
        )

    def test_only_eligible_for_human_review_returns_success(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            result = self.run_cli(folder, {
                "baseline": evaluation("baseline", 2, ["a", "b", "c", "d"]),
                "candidate": evaluation("candidate", 3, ["a", "b", "c", "d"]),
                "safety": evaluation("safety", 6, SAFETY_IDS),
            })
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["decision"], "eligible_for_human_review")
        self.assertFalse(payload["automatic_activation"])

    def test_unverified_holdout_is_rejected_without_activation(self):
        candidate = evaluation("candidate", 4, ["a", "b", "c", "d"])
        candidate.pop("training_overlap_audit")
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_cli(Path(temp), {
                "baseline": evaluation("baseline", 2, ["a", "b", "c", "d"]),
                "candidate": candidate,
                "safety": evaluation("safety", 6, SAFETY_IDS),
            })
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(payload["decision"], "rejected")
        self.assertIn("candidate_holdout_overlap_unverified", payload["reasons"])

    def test_malformed_input_fails_closed_with_sanitized_output(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            baseline = folder / "baseline.json"
            baseline.write_text("not-json", encoding="utf-8")
            candidate = folder / "candidate.json"
            candidate.write_text("{}", encoding="utf-8")
            safety = folder / "safety.json"
            safety.write_text("{}", encoding="utf-8")
            root = Path(__file__).resolve().parents[1]
            result = subprocess.run([
                sys.executable, str(root / "tools" / "check_lora_candidate.py"),
                "--baseline", str(baseline), "--candidate", str(candidate),
                "--safety", str(safety),
            ], cwd=root, capture_output=True, text=True, timeout=10, check=False)
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["decision"], "preflight_failed")
        self.assertNotIn(temp, result.stdout)


if __name__ == "__main__":
    unittest.main()

