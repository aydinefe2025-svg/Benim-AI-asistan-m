import unittest
from datetime import datetime, timezone

from core.authorized_queue_panel import format_queue_event


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


if __name__ == "__main__":
    unittest.main()
