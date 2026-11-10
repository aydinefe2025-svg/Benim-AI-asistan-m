"""Safety and validation tests for reading the public scheduled colony artifact."""
import hashlib
import io
import json
import zipfile
import unittest
from unittest.mock import Mock

from organism_lab.automation_status import (
    ColonyStatusUnavailable, PUBLISHED_STATUS_URL, RUNS_URL, load_latest_colony_status,
    _load_process_cached,
)


def fixture_report(run_id=11):
    return {
        "github_run_id": str(run_id),
        "db_integrity": "ok",
        "mode": "bounded_virtual_reproduction_with_held_out_validation",
        "cycle": {"tick_id": 7},
        "continuity": {"increment_verified": True, "previous_tick_id": 6},
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


def zipped_report(report):
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("colony-cycle.json", json.dumps(report).encode("utf-8"))
    return memory.getvalue()


class FakeResponse:
    def __init__(self, data=None, content=None):
        self.data = data
        self.content = content
        self.headers = {"Content-Length": str(len(content))} if content is not None else {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.data

    def iter_content(self, chunk_size):
        yield self.content


class AutomationStatusTests(unittest.TestCase):
    def test_process_cache_shares_success_and_allows_explicit_refresh(self):
        import organism_lab.automation_status as status_module
        with status_module._STATUS_CACHE_LOCK:
            status_module._STATUS_CACHE_VALUE = None
            status_module._STATUS_CACHE_ERROR = None
            status_module._STATUS_CACHE_UNTIL = 0
        calls = []

        def loader():
            calls.append(True)
            return {"state": "success", "run_id": len(calls)}

        self.assertEqual(_load_process_cached(loader)["run_id"], 1)
        self.assertEqual(_load_process_cached(loader)["run_id"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(_load_process_cached(loader, force_refresh=True)["run_id"], 2)
        self.assertEqual(len(calls), 2)

    def _load(self, report):
        run_id = 11
        archive = zipped_report(report)
        digest = "sha256:" + hashlib.sha256(archive).hexdigest()
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            if url == RUNS_URL:
                return FakeResponse({"workflow_runs": [{
                    "id": run_id, "status": "completed", "conclusion": "success",
                }]})
            if url.endswith(f"/actions/runs/{run_id}/artifacts"):
                return FakeResponse({"artifacts": [{
                    "id": 42, "name": f"cano-colony-cycle-{run_id}",
                    "expired": False, "size_in_bytes": len(archive), "digest": digest,
                }]})
            return FakeResponse(content=archive)

        return load_latest_colony_status(get), calls

    def test_reads_latest_report_and_four_independent_agent_results(self):
        value, calls = self._load(fixture_report())
        self.assertEqual(value["report"]["tick_id"], 7)
        self.assertEqual(len(value["report"]["specialist_agents"]), 4)
        self.assertEqual(value["state"], "success")
        self.assertEqual(len(calls), 4)
        self.assertTrue(calls[-1][1]["stream"])

    def test_prefers_published_static_feed_without_github_api_calls(self):
        report = fixture_report()
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(report)

        value = load_latest_colony_status(get)
        self.assertEqual(value["state"], "success")
        self.assertEqual(value["run_id"], 11)
        self.assertEqual(value["report"]["tick_id"], 7)
        self.assertEqual([call[0] for call in calls], [PUBLISHED_STATUS_URL])

    def test_rejects_invalid_published_report_instead_of_trusting_it(self):
        report = fixture_report()
        report["specialist_agents"]["roles"].clear()
        with self.assertRaises(ColonyStatusUnavailable):
            load_latest_colony_status(lambda url, **kwargs: FakeResponse(report))

    def test_rejects_report_from_a_different_run(self):
        report = fixture_report(run_id=999)
        with self.assertRaises(ColonyStatusUnavailable):
            self._load(report)

    def test_rejects_missing_or_unpassed_agents(self):
        report = fixture_report()
        report["specialist_agents"]["roles"].pop()
        with self.assertRaises(ColonyStatusUnavailable):
            self._load(report)

    def test_no_actions_run_returns_clear_empty_state(self):
        value = load_latest_colony_status(
            lambda url, **kwargs: FakeResponse({"workflow_runs": []})
        )
        self.assertEqual(value["state"], "no_runs")

    def test_no_credentials_are_sent(self):
        _, calls = self._load(fixture_report())
        self.assertTrue(all("Authorization" not in call[1]["headers"] for call in calls))

