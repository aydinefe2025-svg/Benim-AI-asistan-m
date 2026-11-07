"""Tests for the static CANO report reader."""
import json
import unittest
from organism_lab.automation_status import ColonyStatusUnavailable, REPORT_URL, load_latest_colony_status

def fixture(run_id=11):
    return {"github_run_id": str(run_id), "db_integrity": "ok",
            "continuity": {"increment_verified": True},
            "mode": "bounded_virtual_reproduction_with_held_out_validation",
            "cycle": {"tick_id": 7},
            "virtual_generation": {"generation_id": 7, "offspring_scope": "bounded toy digital VM only",
                "model_weights_updated": False, "lesson_status": "rejected",
                "candidate_mutation_rate": 0.05, "next_generation_mutation_rate": 0.02,
                "training": {"ci95_low": -0.1, "candidate_mean_births": 6.0, "candidate_mean_final_population": 12.0},
                "held_out_confirmation": {"ci95_low": 0.2}},
            "specialist_agents": {"status": "passed", "launched": 4, "roles": [
                {"role": role, "label": role, "status": "passed",
                 "execution": "isolated_read_only_subprocess", "model_calls": 0, "checks": ["verified"]}
                for role in ("evidence", "generation", "continuity", "security")]},
            "timestamp": "2026-11-07T00:00:00+00:00"}

class Response:
    def __init__(self, data):
        self.data = data
        self.content = json.dumps(data).encode()
    def raise_for_status(self): pass
    def json(self): return self.data

class Tests(unittest.TestCase):
    def load_report(self, report):
        calls = []
        def get(url, **kwargs):
            calls.append((url, kwargs))
            return Response(report)
        return load_latest_colony_status(get), calls

    def test_static_report_and_agents(self):
        value, calls = self.load_report(fixture())
        self.assertEqual(value["report"]["tick_id"], 7)
        self.assertEqual(len(value["report"]["specialist_agents"]), 4)
        self.assertEqual(value["state"], "success")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].startswith(REPORT_URL + "?v="))
        self.assertNotIn("api.github.com", calls[0][0])
        self.assertNotIn("Authorization", calls[0][1]["headers"])

    def test_run_id_and_agent_validation(self):
        with self.assertRaises(ColonyStatusUnavailable): self.load_report(fixture(999))
        bad = fixture(); bad["specialist_agents"]["roles"].pop()
        with self.assertRaises(ColonyStatusUnavailable): self.load_report(bad)

    def test_invalid_run_id(self):
        with self.assertRaises(ColonyStatusUnavailable): self.load_report({"github_run_id": "../invalid"})

    def test_report_size_is_bounded(self):
        class Oversized(Response):
            def __init__(self): self.content = b"x" * 1000001
            def json(self): return fixture()
        with self.assertRaises(ColonyStatusUnavailable):
            load_latest_colony_status(lambda url, **kwargs: Oversized())
