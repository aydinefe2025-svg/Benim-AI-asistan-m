"""Pure security preflight for the future PostgreSQL queen lease.

No PostgreSQL server or real credentials. End-to-end concurrent behavior is
checked separately by the disposable PostgreSQL integration workflow.
"""
import unittest

from core.postgres_leader_lease import (
    LeaderToken, PostgresLeaderLease, credential_digest,
)

CAPABILITY = "synthetic-random-looking-ci-token-0123456789"


def store(owner="oidc_owner_a", node="queen-a"):
    def unexpected_connect(*args, **kwargs):
        raise AssertionError("Invalid input must not reach PostgreSQL")
    return PostgresLeaderLease(
        "postgresql://unused", owner_key=owner, node_id=node,
        node_secret=CAPABILITY, connect=unexpected_connect)


class LeaderPreflightTests(unittest.TestCase):
    def test_registered_node_capabilities_are_owner_and_node_scoped(self):
        a = credential_digest("oidc_a", "node_a", CAPABILITY)
        self.assertEqual(len(a), 32)
        self.assertNotEqual(a, credential_digest("oidc_b", "node_a", CAPABILITY))
        self.assertNotEqual(a, credential_digest("oidc_a", "node_b", CAPABILITY))
        with self.assertRaises(ValueError):
            credential_digest("oidc_a", "node_a", "weak")

    def test_fail_closed_before_connection_for_bad_scope_ttl(self):
        s = store()
        for scope in ("", "../other", "with spaces", "GLOBAL", "école"):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                s.acquire(scope)
        for ttl in (0, -1, 61, 1.5, True):
            with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                s.acquire("main", ttl_seconds=ttl)

    def test_cross_owner_or_node_token_rejected_before_connection(self):
        s = store()
        for token in (LeaderToken("other_owner", "main", "queen-a", 1),
                      LeaderToken("oidc_owner_a", "main", "queen-b", 1),
                      LeaderToken("oidc_owner_a", "main", "queen-a", 0)):
            with self.subTest(token=token), self.assertRaises(PermissionError):
                s.renew(token)
            with self.subTest(token=token), self.assertRaises(PermissionError):
                s.release(token)

    def test_authorization_node_row_is_transactionally_locked(self):
        # No real credentials or database: assert the SQL lock contract.
        # A shared node lock serializes admin UPDATE enabled=FALSE against
        # an in-flight fenced database mutation.
        class Cursor:
            sql = ""
            params = ()
            def execute(self, sql, params=None):
                self.sql, self.params = sql, params
            def fetchone(self):
                return (credential_digest("oidc_owner_a", "queen-a", CAPABILITY),)
        cursor = Cursor()
        store()._authorize(cursor)
        self.assertIn("FOR SHARE", cursor.sql.upper())
        self.assertEqual(cursor.params, ("oidc_owner_a", "queen-a"))

    def test_empty_owner_and_invalid_node_rejected(self):
        for owner,node in (("", "queen-a"),("oidc_a", "../other"),
                           ("oidc_a","node with spaces")):
            with self.subTest(owner=owner,node=node), self.assertRaises(ValueError):
                store(owner,node)


    def test_reject_autocommit_cursor_before_authorization(self):
        # With autocommit=True the SELECT FOR UPDATE lock would end before
        # the caller's subsequent mutation: fencing would be ineffective.
        from datetime import datetime, timedelta, timezone
        from unittest.mock import Mock, patch
        from core.postgres_leader_lease import LeaderToken
        lease = store()
        cursor = Mock()
        cursor.connection.autocommit = True
        cursor.fetchone.side_effect = [
            ("queen-a", 1, datetime.now(timezone.utc) + timedelta(seconds=30)),
            (True,),
        ]
        with patch.object(lease, "_authorize", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "transaction"):
                lease.assert_fence(cursor, LeaderToken("oidc_owner_a", "main", "queen-a", 1))
        cursor.execute.assert_not_called()

    def test_reject_uninspectable_connection_before_authorization(self):
        # A cursor without an inspectable owning connection must not be
        # accepted as proof of a durable transactional row lock.
        from datetime import datetime, timedelta, timezone
        from unittest.mock import Mock, patch
        from core.postgres_leader_lease import LeaderToken
        lease = store()
        cursor = Mock(spec=["execute", "fetchone"])
        cursor.fetchone.side_effect = [
            ("queen-a", 1, datetime.now(timezone.utc) + timedelta(seconds=30)),
            (True,),
        ]
        with patch.object(lease, "_authorize", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "transaction"):
                lease.assert_fence(cursor, LeaderToken("oidc_owner_a", "main", "queen-a", 1))
        cursor.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
