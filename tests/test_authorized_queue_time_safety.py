"""Fail-closed lease boundary and time-injection regressions for CANO queues.

Only synthetic owner/task IDs; PostgreSQL tests use a fake cursor and prove
invalid inputs are rejected *before* any database connection is attempted.
"""
import math
import tempfile
import unittest
from pathlib import Path

from core.authorized_queue import AuthorizedQueue
from core.postgres_authorized_queue import PostgresAuthorizedQueue


class _LeaseCursor:
    def __init__(self):
        self.sql = []
    def execute(self, statement, params=None):
        self.sql.append((statement, params))
    def fetchone(self):
        return {"id": "task", "state": "running",
                "lease_token": "synthetic-token", "lease_until": 105.0}


class LocalQueueTimeSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.queue = AuthorizedQueue(str(Path(temp.name) / "queue.sqlite"),
                                     owner_key="synthetic-owner")

    def test_exact_lease_expiry_rejects_completion(self):
        job = self.queue.enqueue("lease-equal", "Synthetic", approved=True)
        lease = self.queue.claim("worker", approved=True, now=100, lease_seconds=5)
        self.assertEqual(job["id"], lease["id"])
        with self.assertRaises(PermissionError):
            self.queue.complete(job["id"], lease["lease_token"], "Draft", now=105)
        self.assertEqual(self.queue.get(job["id"])["state"], "running")

    def test_exact_expiry_recovery_blocks_lease(self):
        job = self.queue.enqueue("recover-equal", "Synthetic", approved=True)
        lease = self.queue.claim("worker", approved=True, now=100, lease_seconds=5)
        self.assertEqual(job["id"], lease["id"])
        self.assertEqual(self.queue.recover_expired(now=105), 1)
        self.assertEqual(self.queue.get(job["id"])["state"], "blocked")

    def test_nonfinite_time_cannot_claim_or_complete(self):
        job = self.queue.enqueue("nonfinite", "Synthetic", approved=True)
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(value=str(bad)):
                with self.assertRaises(ValueError):
                    self.queue.claim("worker", approved=True, now=bad)
        lease = self.queue.claim("worker", approved=True, now=100, lease_seconds=5)
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(completion=str(bad)):
                with self.assertRaises(ValueError):
                    self.queue.complete(job["id"], lease["lease_token"], "Draft", now=bad)
                with self.assertRaises(ValueError):
                    self.queue.fail(job["id"], lease["lease_token"], now=bad)
                with self.assertRaises(ValueError):
                    self.queue.recover_expired(now=bad)
        self.assertEqual(self.queue.get(job["id"])["state"], "running")


class PostgresQueueTimeSafetyTests(unittest.TestCase):
    def setUp(self):
        def no_db(*_args, **_kwargs):
            raise AssertionError("Invalid input must not open PostgreSQL")
        self.queue = PostgresAuthorizedQueue(
            "postgresql://synthetic-unused",
            owner_key="synthetic-owner", connect=no_db)

    def test_exact_lease_expiry_rejects_completion(self):
        with self.assertRaises(PermissionError):
            self.queue._require_lease(
                _LeaseCursor(), "task", "synthetic-token", 105.0)

    def test_production_rejects_finite_clock_override_before_connect(self):
        # CI may inject clocks only through an explicit test-only construction.
        for operation in (
            lambda: self.queue.claim("worker", approved=True, now=100),
            lambda: self.queue.complete("task", "token", "draft", now=100),
            lambda: self.queue.fail("task", "token", now=100),
            lambda: self.queue.recover_expired(now=100),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(PermissionError):
                    operation()

    def test_nonfinite_time_fails_before_database_connection(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(value=str(bad)):
                with self.assertRaises(ValueError):
                    self.queue.claim("worker", approved=True, now=bad)
                with self.assertRaises(ValueError):
                    self.queue.complete("task", "synthetic-token", "Draft", now=bad)
                with self.assertRaises(ValueError):
                    self.queue.fail("task", "synthetic-token", now=bad)
                with self.assertRaises(ValueError):
                    self.queue.recover_expired(now=bad)


if __name__ == "__main__":
    unittest.main()
