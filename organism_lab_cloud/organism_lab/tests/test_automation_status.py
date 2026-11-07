"""Safety and validation tests for reading the published colony report."""
import json
import unittest

from organism_lab.automation_status import (
    ColonyStatusUnavailable, RAW_REPORT_URL, load_latest_colony_status,
)


def fixture_report(run_id=11):
    return {
        "github_run_id": str(run_id),
        "db_integrity": "ok",
        "continuity": {"increment_verified": True},
        "mode": "bounded_virtual_reproduction_with_held_out_validation",
        "cycle": {"tick_id": 7},
        "virtual_generation": {
            "generation_id": 7, "offspring_scope": "bounded toy digital VM only",
            "model_weights_updated": False, "lesson_status": "rejected",
            "candidate_mutation_rate": 0.05, "next_generation_mutation_rate": 0.02,
            "training": {"ci95_low": -0.1, "candidate_mean_births": 6.0,
                         "candidate_mean_final_population": 12.0},
            "held_out_confirmation": {"ci95_low": 0.2},
        },
        "specialist_agents": {
            "status": "passed", "launched": 4,
            "roles": [
                {"role": role, "label": role, "status": "passed",
                 "execution": "isolated_read_only_subprocess", "model_calls": 0,
                 "checks": ["verified"]}
                for role in ("evidence", "generation", "continuity", "security")
            ],
        },
        "timestamp": "2026-11-07T00:00:00+00:00",
    }


class FakeResponse:
    def __init__(self, content):
        self.content = content
        self.headers = {"Content-Length": str(len(content))}

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield self.content


class AutomationStatusTests(unittest.TestCase):
    def _load(self, report):
        content = json.dumps(report).encode("utf-8")
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            if url != RAW_REPORT_URL:
                raise AssertionError("The panel must use the published raw report only")
            return FakeResponse(content)

        return load_latest_colony_status(get), calls

    def test_reads_published_report_and_four_independent_agent_results(self):
        value, calls = self._load(fixture_report())
        self.assertEqual(value["report"]["tick_id"], 7)
        self.assertEqual(len(value["report"]["specialist_agents"]), 4)
        self.assertEqual(value["state"], "success")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][1]["stream"])
        self.assertNotIn("Authorization", calls[0][1]["headers"])

    def test_rejects_report_with_invalid_run_id(self):
        report = fixture_report()
        report["github_run_id"] = "not-a-run"
        with self.assertRaises(ColonyStatusUnavailable):
            self._load(report)

    def test_rejects_report_from_wrong_mode_or_corrupt_state(self):
        for field, value in (("mode", "unbounded"), ("db_integrity", "failed")):
            report = fixture_report()
            report[field] = value
            with self.assertRaises(ColonyStatusUnavailable):
                self._load(report)

    def test_rejects_missing_or_unpassed_agents(self):
        report = fixture_report()
        report["specialist_agents"]["roles"].pop()
        with self.assertRaises(ColonyStatusUnavailable):
            self._load(report)

    def test_rejects_oversized_report_before_parsing(self):
        content = b" " * 1_000_001

        def get(url, **kwargs):
            return FakeResponse(content)

        with self.assertRaises(ColonyStatusUnavailable):
            load_latest_colony_status(get)

    def test_rejects_report_exceeding_stream_limit(self):
        class UnboundedResponse(FakeResponse):
            def __init__(self):
                super().__init__(b"{}")
                self.headers = {}

            def iter_content(self, chunk_size):
                yield b" " * 1_000_001

        with self.assertRaises(ColonyStatusUnavailable):
            load_latest_colony_status(lambda url, **kwargs: UnboundedResponse())
