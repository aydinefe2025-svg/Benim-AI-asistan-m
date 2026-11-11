import json
import unittest
from datetime import datetime, timedelta, timezone

from scripts.cano_schedule_guard import MAX_REPORT_AGE, should_run_cycle


def valid_report(timestamp):
    roles = ("evidence", "generation", "continuity", "security")
    return {
        "timestamp": timestamp,
        "db_integrity": "ok",
        "stored_ticks": 12,
        "verified_tick_id": 12,
        "continuity": {
            "had_prior_state": True,
            "previous_tick_id": 11,
            "previous_tick_count": 11,
            "increment_verified": True,
        },
        "cycle": {"tick_id": 12, "state": "proposed"},
        "virtual_generation": {"generation_id": 12, "lesson_status": "rejected"},
        "mode": "bounded_virtual_reproduction_with_held_out_validation",
        "scope": "authorized_github_runner",
        "specialist_agents": {
            "status": "passed",
            "launched": 4,
            "roles": [
                {
                    "role": role,
                    "status": "passed",
                    "execution": "isolated_read_only_subprocess",
                    "model_calls": 0,
                }
                for role in roles
            ],
        },
    }


class CanoScheduleGuardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

    def report(self, timestamp, **overrides):
        payload = valid_report(timestamp)
        payload.update(overrides)
        return json.dumps(payload).encode()

    def test_manual_and_push_events_always_run(self):
        for event in ("workflow_dispatch", "push"):
            with self.subTest(event=event):
                self.assertTrue(should_run_cycle(event, None, now=self.now))

    def test_recent_complete_scheduled_report_skips_cycle(self):
        recent = self.now - timedelta(minutes=49, seconds=59)
        self.assertFalse(should_run_cycle("schedule", self.report(recent.isoformat()), now=self.now))

    def test_recent_transferred_generation_does_not_run_duplicate_cycle(self):
        """The generator and specialist validator both publish 'transferred'."""
        recent = self.now - timedelta(minutes=5)
        report = valid_report(recent.isoformat())
        report["virtual_generation"]["lesson_status"] = "transferred"
        self.assertFalse(
            should_run_cycle("schedule", json.dumps(report).encode(), now=self.now)
        )

    def test_unknown_accepted_generation_fails_open(self):
        """'accepted' is not a persisted value of the canonical generator."""
        recent = self.now - timedelta(minutes=5)
        report = valid_report(recent.isoformat())
        report["virtual_generation"]["lesson_status"] = "accepted"
        self.assertTrue(
            should_run_cycle("schedule", json.dumps(report).encode(), now=self.now)
        )

    def test_threshold_and_older_report_trigger_cycle(self):
        stale = self.now - MAX_REPORT_AGE
        self.assertTrue(should_run_cycle("schedule", self.report(stale.isoformat()), now=self.now))

    def test_missing_malformed_or_oversized_report_fails_open(self):
        for payload in (None, b"", b"{", b"x" * 1_000_001):
            with self.subTest(payload=payload if len(payload or b"") < 10 else "oversized"):
                self.assertTrue(should_run_cycle("schedule", payload, now=self.now))

    def test_missing_or_timezone_naive_timestamp_fails_open(self):
        for payload in (b"{}", self.report("2026-11-09T11:00:00")):
            with self.subTest(payload=payload):
                self.assertTrue(should_run_cycle("schedule", payload, now=self.now))

    def test_future_timestamp_fails_open(self):
        future = self.now + timedelta(seconds=1)
        self.assertTrue(should_run_cycle("schedule", self.report(future.isoformat()), now=self.now))

    def test_fresh_but_invalid_reports_fail_open(self):
        recent = (self.now - timedelta(minutes=1)).isoformat()
        invalid = (
            {"db_integrity": "failed"},
            {"mode": "unbounded"},
            {"continuity": {"had_prior_state": True}},
            {"specialist_agents": {"status": "failed"}},
        )
        for override in invalid:
            with self.subTest(override=override):
                self.assertTrue(should_run_cycle(
                    "schedule", self.report(recent, **override), now=self.now))

    def test_no_prior_state_is_valid_for_initial_cycle(self):
        recent = (self.now - timedelta(minutes=1)).isoformat()
        initial = valid_report(recent)
        initial["continuity"] = {"had_prior_state": False}
        initial["stored_ticks"] = 1
        initial["verified_tick_id"] = 1
        initial["cycle"]["tick_id"] = 1
        initial["virtual_generation"]["generation_id"] = 1
        self.assertFalse(should_run_cycle(
            "schedule", json.dumps(initial), now=self.now))


if __name__ == "__main__":
    unittest.main()
