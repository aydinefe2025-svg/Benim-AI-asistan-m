"""Regression: do not expose failed Postgres failure-acknowledgements.

The provider callback may already have spent its approved call budget.
A failed DB error-state write must not leak secrets or auto-retry.
No real DB and no model calls.
"""
import unittest
from core.postgres_authorized_queue import PostgresAuthorizedQueue

class BrokenFailQueue(PostgresAuthorizedQueue):
    def __init__(self):
        super().__init__("postgresql://unused", owner_key="synthetic",
                         connect=lambda *args, **kwargs: (_ for _ in ()).throw(
                             AssertionError("No real database allowed")))
        self.fail_attempts = 0

    def claim(self, worker_id, *, approved=False, now=None, lease_seconds=60):
        return {"id": "synthetic-task", "goal": "test", "lease_token": "synthetic"}

    def renew_lease(self, task_id, lease_token, *, lease_seconds=60):
        return True

    def fail(self, task_id, lease_token, *, now=None):
        self.fail_attempts += 1
        raise RuntimeError("SENSITIVE-POSTGRES-PASSWORD=should-not-be-shown")

class FailurePersistenceUncertainTests(unittest.TestCase):
    def _assert_fail_closed(self, answer):
        queue = BrokenFailQueue()
        result = queue.run_once("synthetic-worker", answer,
                                approved=True, lease_seconds=60)
        self.assertEqual(result["status"], "failure_uncertain")
        self.assertTrue(result["manual_review"])
        self.assertFalse(result["verified"])
        self.assertEqual(queue.fail_attempts, 1)
        self.assertNotIn("SENSITIVE", str(result))

    def test_callback_exception_and_failed_database_ack(self):
        def raises(_):
            raise RuntimeError("PRIVATE-PROVIDER-RESPONSE")
        self._assert_fail_closed(raises)

    def test_empty_reply_and_failed_database_ack(self):
        self._assert_fail_closed(lambda _: "   ")

if __name__ == "__main__":
    unittest.main()

