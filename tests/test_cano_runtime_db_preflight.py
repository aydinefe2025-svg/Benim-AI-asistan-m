import unittest
from core.cano_runtime_db_preflight import (
    preflight_authorized_queue,
    preflight_task_store,
)


class TaskPreflightTests(unittest.TestCase):
    def test_lab_preflight_is_read_only_and_returns_no_owner_key(self):
        from core import cano_runtime_db_preflight as m
        self.assertTrue(callable(getattr(m, "preflight_organism_lab", None)))
        seen = []
        class LabStore:
            def __init__(self, owner_key, database_url):
                seen.append((owner_key, database_url))
            def verify_schema(self):
                seen.append("verified")
                return "cano_snapshot_app"
        report = m.preflight_organism_lab(
            "postgresql://SECRET_TOKEN", store_factory=LabStore
        )
        self.assertEqual(report, {"ok": True, "reason": "verified"})
        self.assertEqual(seen[-1], "verified")
        self.assertEqual(seen[0][0], "oidc_" + "0" * 64)
        self.assertNotIn("SECRET_TOKEN", repr(report))
        self.assertNotIn("oidc_", repr(report))

    def test_lab_preflight_classifies_rls_denial_without_secrets(self):
        from core import cano_runtime_db_preflight as m
        from core.organism_lab_persistence import OrganismLabRlsPolicyError
        self.assertTrue(callable(getattr(m, "preflight_organism_lab", None)))
        class InvalidRole:
            def __init__(self, owner_key, database_url):
                pass
            def verify_schema(self):
                raise OrganismLabRlsPolicyError("PASSWORD=PRIVATE")
        report = m.preflight_organism_lab(
            "postgresql://PRIVATE", store_factory=InvalidRole
        )
        self.assertFalse(report["ok"])
        self.assertEqual(report["error_type"], "OrganismLabRlsPolicyError")
        self.assertNotIn("PRIVATE", repr(report))

    def test_app_invokes_lab_startup_preflight_under_existing_one_shot_gate(self):
        from pathlib import Path
        app = (Path(__file__).resolve().parents[1] / "app.py").read_text("utf-8")
        self.assertIn("preflight_organism_lab(", app)
        self.assertIn("CANO_ORGANISM_LAB_PREFLIGHT", app)

    def test_good_read_only_schema(self):
        called = []
        class Store:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
            def verify_schema(self):
                called.append(self.kwargs)
        result = preflight_task_store("postgresql://secret_here", store_factory=Store)
        self.assertEqual({"ok": True, "reason": "verified"}, result)
        self.assertEqual("read_only_preflight", called[0]["owner_key"])

    def test_failure_redacts_credentials(self):
        class OperationalError(Exception):
            sqlstate = "28P01"
        class Store:
            def __init__(self, **kwargs): pass
            def verify_schema(self):
                raise OperationalError("postgresql://PRIVATE_PASSWORD@example.com")
        result = preflight_task_store("postgresql://SECRET_USER", store_factory=Store)
        self.assertFalse(result["ok"])
        self.assertEqual("OperationalError", result["error_type"])
        self.assertEqual("28P01", result["sqlstate"])
        self.assertNotIn("PRIVATE_PASSWORD", repr(result))
        self.assertNotIn("SECRET_USER", repr(result))

    def test_absent_database_never_calls_store(self):
        result = preflight_task_store(
            "", store_factory=lambda **kwargs: self.fail("connected")
        )
        self.assertEqual("not_configured", result["reason"])

    def test_unknown_exception_fails_closed(self):
        class Bad:
            def __init__(self, **kwargs):
                raise RuntimeError("PRIVATE_TOKEN")
        result = preflight_task_store("postgresql://redacted", store_factory=Bad)
        self.assertFalse(result["ok"])
        self.assertEqual("OtherDatabaseError", result["error_type"])
        self.assertNotIn("PRIVATE_TOKEN", repr(result))

    def test_authorized_queue_uses_read_only_identity_and_verifies_schema(self):
        called = []
        class Queue:
            def __init__(self, **kwargs):
                called.append(kwargs)
            def verify_schema(self):
                called.append("verified")
        result = preflight_authorized_queue(
            "postgresql://secret_here", queue_factory=Queue
        )
        self.assertEqual({"ok": True, "reason": "verified"}, result)
        self.assertEqual("read_only_preflight", called[0]["owner_key"])
        self.assertEqual("verified", called[1])

    def test_authorized_queue_failure_is_sanitized(self):
        class InsufficientPrivilege(Exception):
            sqlstate = "42501"
        class Queue:
            def __init__(self, **kwargs): pass
            def verify_schema(self):
                raise InsufficientPrivilege("password=PRIVATE_TOKEN")
        result = preflight_authorized_queue(
            "postgresql://SECRET", queue_factory=Queue
        )
        self.assertFalse(result["ok"])
        self.assertEqual("InsufficientPrivilege", result["error_type"])
        self.assertEqual("42501", result["sqlstate"])
        self.assertNotIn("PRIVATE_TOKEN", repr(result))
        self.assertNotIn("SECRET", repr(result))

    def test_authorized_queue_does_not_connect_without_database(self):
        result = preflight_authorized_queue(
            "", queue_factory=lambda **kwargs: self.fail("connected")
        )
        self.assertEqual("not_configured", result["reason"])


if __name__ == "__main__":
    unittest.main()
