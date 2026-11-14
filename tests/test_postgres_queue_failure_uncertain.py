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


class PermissionFailureQueue(BrokenFailQueue):
    """A backend permission error is not proof that the lease is gone."""

    def fail(self, task_id, lease_token, *, now=None):
        self.fail_attempts += 1
        raise PermissionError("SENSITIVE-DB-ACL-DENIED")


class PermissionCompletionQueue(BrokenFailQueue):
    def complete(self, task_id, lease_token, draft, *, now=None):
        raise PermissionError("SENSITIVE-DB-COMMIT-UNKNOWN")


class ExplicitLeaseLossQueue(BrokenFailQueue):
    def fail(self, task_id, lease_token, *, now=None):
        from core.postgres_authorized_queue import LeaseLostError
        raise LeaseLostError("lease lost")


class PermissionErrorClassificationTests(unittest.TestCase):
    def test_permission_error_is_not_lease_loss_on_failure_ack(self):
        queue = PermissionFailureQueue()
        result = queue.run_once(
            "synthetic-worker", lambda _: (_ for _ in ()).throw(
                RuntimeError("SENSITIVE-PROVIDER-CALL")),
            approved=True,
        )
        self.assertEqual(result["status"], "failure_uncertain")
        self.assertTrue(result["manual_review"])
        self.assertFalse(result["verified"])
        self.assertEqual(queue.fail_attempts, 1)
        self.assertNotIn("SENSITIVE", str(result))

    def test_permission_error_is_not_lease_loss_on_completion_ack(self):
        queue = PermissionCompletionQueue()
        result = queue.run_once(
            "synthetic-worker", lambda _: "synthetic answer",
            approved=True,
        )
        self.assertEqual(result["status"], "completion_uncertain")
        self.assertTrue(result["manual_review"])
        self.assertFalse(result["verified"])
        self.assertNotIn("SENSITIVE", str(result))

    def test_explicit_lease_loss_is_distinct_from_backend_denial(self):
        from core.postgres_authorized_queue import LeaseLostError
        self.assertTrue(issubclass(LeaseLostError, PermissionError))
        queue = ExplicitLeaseLossQueue()
        result = queue.run_once(
            "synthetic-worker", lambda _: (_ for _ in ()).throw(
                RuntimeError("synthetic provider error")),
            approved=True,
        )
        self.assertEqual(result["status"], "lease_lost")
        self.assertFalse(result["verified"])
        self.assertNotIn("manual_review", result)



class RenewalDeniedQueue(BrokenFailQueue):
    def __init__(self):
        super().__init__()
        from threading import Event
        self.renewed = Event()

    def renew_lease(self, task_id, lease_token, *, lease_seconds=60):
        self.renewed.set()
        raise PermissionError("SENSITIVE-DB-RENEWAL-DENIED")


class RenewalLeaseLostQueue(RenewalDeniedQueue):
    def renew_lease(self, task_id, lease_token, *, lease_seconds=60):
        from core.postgres_authorized_queue import LeaseLostError
        self.renewed.set()
        raise LeaseLostError("confirmed expired lease")


class LeaseRenewalUncertaintyTests(unittest.TestCase):
    def _callback_after_renewal(self, queue):
        import time
        def synthetic(_):
            self.assertTrue(queue.renewed.wait(timeout=3))
            # Allow the renewal thread to publish its outcome before returning.
            time.sleep(.05)
            return "synthetic answer"
        return synthetic

    def test_database_permission_error_on_renewal_needs_manual_review(self):
        queue = RenewalDeniedQueue()
        result = queue.run_once("synthetic-worker",
                                self._callback_after_renewal(queue),
                                approved=True, lease_seconds=1)
        self.assertEqual(result["status"], "lease_renewal_uncertain")
        self.assertTrue(result["manual_review"])
        self.assertFalse(result["verified"])
        self.assertNotIn("SENSITIVE", str(result))

    def test_confirmed_renewal_expiry_is_distinct(self):
        queue = RenewalLeaseLostQueue()
        result = queue.run_once("synthetic-worker",
                                self._callback_after_renewal(queue),
                                approved=True, lease_seconds=1)
        self.assertEqual(result["status"], "lease_lost")
        self.assertFalse(result["verified"])


class FailureUncertainPanelTests(unittest.TestCase):
    def test_uncertain_failure_requires_manual_review_not_retry_hint(self):
        from unittest.mock import MagicMock, patch
        from core.authorized_queue_panel import render_authorized_queue_panel
        for state in ("failure_uncertain", "completion_uncertain"):
            with self.subTest(status=state):
                st = MagicMock()
                st.form_submit_button.side_effect = (False, True)
                st.checkbox.return_value = True
                queue = MagicMock()
                queue.list.return_value = []
                queue.run_once.return_value = {
                    "status": state, "manual_review": True, "verified": False
                }
                with patch("core.authorized_queue_panel.PostgresAuthorizedQueue",
                           return_value=queue):
                    render_authorized_queue_panel(
                        st, answer=lambda _: "never called",
                        owner_key="synthetic-owner",
                        database_url="postgresql://synthetic-unused")
                queue.run_once.assert_called_once()
                warnings = [str(call.args[0]) for call in st.warning.call_args_list]
                self.assertTrue(any(
                    "manuel" in message.lower() and "yeniden" in message.lower()
                    for message in warnings), warnings)


if __name__ == "__main__":
    unittest.main()

