import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from core.authorized_queue_panel import format_queue_event, render_authorized_queue_panel


class AuthorizedQueueAuditTests(unittest.TestCase):
    def test_known_queue_events_are_human_readable(self):
        event = {
            "at": 0,
            "state": "queued",
            "code": "retry_requires_explicit_run",
            "job_id": "private-id",
            "owner_key": "private-owner",
        }
        rendered = format_queue_event(event)
        self.assertIn("1970-01-01 00:00:00 UTC", rendered)
        self.assertIn("Kuyrukta", rendered)
        self.assertIn("yeni kullanıcı onayı", rendered)
        self.assertNotIn("private-id", rendered)
        self.assertNotIn("private-owner", rendered)
        self.assertNotIn("retry_requires_explicit_run", rendered)

    def test_known_event_codes_cover_success_retry_budget_and_expiry(self):
        cases = [
            ("queued", "explicit_approval", "kuyruğa eklendi"),
            ("running", "authorized_claim", "başlatıldı"),
            ("review_pending", "unverified_draft_saved", "Doğrulanmamış"),
            ("blocked", "call_budget_exhausted", "bütçesi tükendi"),
            ("blocked", "lease_expired_manual_review", "manuel inceleme"),
        ]
        for state, code, expected in cases:
            with self.subTest(code=code):
                self.assertIn(expected, format_queue_event({
                    "at": 1, "state": state, "code": code,
                }))

    def test_unknown_fields_are_not_echoed_and_bad_time_is_safe(self):
        rendered = format_queue_event({
            "at": "not-a-date", "state": "unexpected-state",
            "code": "secret-token-value",
        })
        self.assertIn("Zaman bilinmiyor", rendered)
        self.assertIn("Durum bilinmiyor", rendered)
        self.assertNotIn("secret-token-value", rendered)
        self.assertNotIn("unexpected-state", rendered)

    def test_datetime_event_uses_utc(self):
        rendered = format_queue_event({
            "at": datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
            "state": "review_pending", "code": "unverified_draft_saved",
        })
        self.assertIn("2026-11-05 12:00:00 UTC", rendered)

    def test_rejects_non_object_event(self):
        with self.assertRaises(ValueError):
            format_queue_event("bad")


class AuthorizedQueueAuditPanelTests(unittest.TestCase):
    def test_panel_reads_and_renders_job_audit_without_mutating_queue(self):
        st = MagicMock()
        st.form_submit_button.return_value = False
        queue = MagicMock()
        queue.list.return_value = [{
            "id": "job-12345678", "state": "queued",
            "attempts": 0, "max_calls": 2, "draft": None,
        }]
        queue.events.return_value = [{
            "at": 0, "state": "queued", "code": "explicit_approval",
        }]
        with patch("core.authorized_queue_panel.PostgresAuthorizedQueue",
                   return_value=queue):
            render_authorized_queue_panel(
                st, owner_key="owner-test", database_url="postgres://test",
            )
        queue.events.assert_called_once_with("job-12345678")
        st.write.assert_any_call(
            "1970-01-01 00:00:00 UTC · Kuyrukta: "
            "İş kullanıcı onayıyla kuyruğa eklendi."
        )
        queue.enqueue.assert_not_called()
        queue.run_once.assert_not_called()
        st.rerun.assert_not_called()


if __name__ == "__main__":
    unittest.main()
