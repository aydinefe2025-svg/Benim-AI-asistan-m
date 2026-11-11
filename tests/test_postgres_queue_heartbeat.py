import threading
import time
import unittest

from core.postgres_authorized_queue import PostgresAuthorizedQueue


class _MemoryQueue(PostgresAuthorizedQueue):
    """Small lease model; no database connection is possible in these tests."""
    def __init__(self, *, renewal_fails=False, callback_error=False):
        super().__init__("postgresql://synthetic-unused", owner_key="owner",
                         connect=lambda *a, **k: self.fail("unexpected database"))
        self.job = {"id": "task", "goal": "synthetic goal", "lease_token": "token"}
        self.deadline = 0.0
        self.renewal_fails = renewal_fails
        self.callback_error = callback_error
        self.completion_error = None
        self.renewals = 0
        self.completed = False
        self.failed = False

    def claim(self, worker_id, *, approved=False, now=None, lease_seconds=60):
        self.deadline = time.monotonic() + lease_seconds
        return dict(self.job)

    def renew_lease(self, task_id, token, *, lease_seconds=60):
        if self.renewal_fails or task_id != "task" or token != "token" or time.monotonic() >= self.deadline:
            raise PermissionError("Job lease expired or lost")
        self.renewals += 1
        self.deadline = time.monotonic() + lease_seconds

    def complete(self, task_id, token, draft, *, now=None):
        if self.completion_error:
            raise RuntimeError(self.completion_error)
        if token != "token" or time.monotonic() >= self.deadline:
            raise PermissionError("Job lease expired or lost")
        self.completed = True
        return {"status": "review_pending", "draft": draft}

    def fail(self, task_id, token, *, now=None):
        self.failed = True
        return {"status": "retry_pending"}


class PostgresQueueHeartbeatTests(unittest.TestCase):
    def test_completion_error_is_uncertain_and_never_fails_job_or_exposes_secret(self):
        queue = _MemoryQueue()
        queue.completion_error = "db password=do-not-leak"
        result = queue.run_once("worker", lambda _: "valid draft", approved=True)
        self.assertEqual(result["status"], "completion_uncertain")
        self.assertEqual(result["manual_review"], True)
        self.assertFalse(queue.failed)
        self.assertNotIn("do-not-leak", str(result))

    def test_long_callback_renews_short_lease_before_saving_draft(self):
        queue = _MemoryQueue()
        result = queue.run_once("worker", lambda _: (time.sleep(1.2), "draft")[1],
                                approved=True, lease_seconds=1)
        self.assertGreaterEqual(queue.renewals, 1)
        self.assertTrue(queue.completed)
        self.assertEqual(result["status"], "review_pending")

    def test_lost_lease_discards_draft_and_does_not_schedule_retry(self):
        queue = _MemoryQueue(renewal_fails=True)
        result = queue.run_once("worker", lambda _: (time.sleep(1.1), "secret draft")[1],
                                approved=True, lease_seconds=1)
        self.assertEqual(result["status"], "lease_lost")
        self.assertFalse(queue.completed)
        self.assertFalse(queue.failed)
        self.assertNotIn("secret draft", str(result))

    def test_callback_error_fails_through_existing_bounded_path(self):
        queue = _MemoryQueue()
        def callback(_):
            raise RuntimeError("private prompt token")
        result = queue.run_once("worker", callback, approved=True)
        self.assertTrue(queue.failed)
        self.assertEqual(result["status"], "retry_pending")
        self.assertNotIn("private prompt", str(result))

    def test_callback_error_stops_renewal_worker(self):
        queue = _MemoryQueue()
        def callback(_):
            raise RuntimeError("provider secret")
        result = queue.run_once("worker", callback, approved=True, lease_seconds=1)
        self.assertEqual(result["status"], "retry_pending")
        previous = queue.renewals
        time.sleep(0.5)
        self.assertEqual(queue.renewals, previous, "heartbeat leaked after callback error")

    def test_empty_result_stops_renewal_worker(self):
        queue = _MemoryQueue()
        result = queue.run_once("worker", lambda _: "", approved=True, lease_seconds=1)
        self.assertEqual(result["status"], "retry_pending")
        previous = queue.renewals
        time.sleep(0.5)
        self.assertEqual(queue.renewals, previous, "heartbeat leaked after empty provider result")

    def test_forged_or_expired_token_cannot_renew(self):
        queue = _MemoryQueue()
        queue.claim("worker", approved=True)
        with self.assertRaises(PermissionError):
            queue.renew_lease("task", "forged-token")
        queue.deadline = time.monotonic() - 1
        with self.assertRaises(PermissionError):
            queue.renew_lease("task", "token")


if __name__ == "__main__":
    unittest.main()
