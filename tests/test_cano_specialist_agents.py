"""The scheduled cycle starts isolated specialist validators and records readback."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.cano_specialist_agents import attach_agent_results, run_agents


def make_fixture(root: Path) -> tuple[Path, Path]:
    database = root / "colony.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE virtual_generation (tick_id INTEGER PRIMARY KEY, lesson_status TEXT NOT NULL)")
        db.execute("INSERT INTO virtual_generation VALUES (1, 'rejected')")
    report = {
        "github_run_id": "42",
        "db_integrity": "ok",
        "stored_ticks": 1,
        "verified_tick_id": 1,
        "continuity": {"increment_verified": True, "previous_tick_id": None,
                       "previous_tick_count": 0},
        "cycle": {"tick_id": 1, "candidates": []},
        "virtual_generation": {
            "generation_id": 1, "candidate_mutation_rate": 0.02,
            "parent_mutation_rate": 0.0, "next_generation_mutation_rate": 0.0,
            "lesson_status": "rejected", "offspring_scope": "bounded toy digital VM only",
            "model_weights_updated": False,
            "training": {"paired_seeds": 12, "ci95_low": -0.1},
            "held_out_confirmation": {"paired_seeds": 12, "ci95_low": 0.2},
        },
        "mode": "bounded_virtual_reproduction_with_held_out_validation",
        "scope": "authorized_github_runner",
    }
    artifact = root / "colony-cycle.json"
    artifact.write_text(json.dumps(report), encoding="utf-8")
    return artifact, database


class SpecialistAgentTests(unittest.TestCase):
    def test_four_separate_agents_pass_and_results_are_read_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact, database = make_fixture(Path(tmp))
            results = attach_agent_results(artifact, database)
            saved = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(len(results), 4)
            self.assertEqual(saved["specialist_agents"]["status"], "passed")
            self.assertEqual(saved["specialist_agents"]["launched"], 4)
            self.assertEqual({item["status"] for item in saved["specialist_agents"]["roles"]}, {"passed"})
            self.assertTrue(all(item["execution"] == "isolated_read_only_subprocess"
                                and item["model_calls"] == 0
                                for item in results))

    def test_transfer_claim_is_rejected_if_confirmation_ci_does_not_support_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact, database = make_fixture(Path(tmp))
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            payload["virtual_generation"].update({
                "lesson_status": "transferred", "next_generation_mutation_rate": 0.02,
                "training": {"paired_seeds": 12, "ci95_low": 0.1},
                "held_out_confirmation": {"paired_seeds": 12, "ci95_low": -0.1},
            })
            artifact.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                run_agents(artifact, database)

    def test_secret_like_content_fails_security_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact, database = make_fixture(Path(tmp))
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            payload["unexpected_note"] = "gsk_" + "A" * 28
            artifact.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                run_agents(artifact, database)
