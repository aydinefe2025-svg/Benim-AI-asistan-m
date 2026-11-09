import json
import unittest
from datetime import datetime, timedelta, timezone

from scripts.cano_schedule_guard import MAX_REPORT_AGE, should_run_cycle


class CanoScheduleGuardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

    def report(self, timestamp):
        return json.dumps({"timestamp": timestamp}).encode()

    def test_manual_and_push_events_always_run(self):
        for event in ("workflow_dispatch", "push"):
            with self.subTest(event=event):
                self.assertTrue(should_run_cycle(event, None, now=self.now))

    def test_recent_scheduled_report_skips_expensive_cycle(self):
        recent = self.now - timedelta(minutes=49, seconds=59)
        self.assertFalse(should_run_cycle("schedule", self.report(recent.isoformat()), now=self.now))

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


if __name__ == "__main__":
    unittest.main()
