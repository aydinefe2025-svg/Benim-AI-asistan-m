import importlib.util
import unittest
from unittest.mock import Mock

class PersistentGrantBoundary(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("core.postgres_local_grant"),
                             "Durable PostgreSQL grant is not implemented")
        from core.postgres_local_grant import PostgresLocalGrant
        self.bridge=PostgresLocalGrant
    def test_issuance_requires_explicit_approval_before_queue_claim(self):
        queue=Mock()
        with self.assertRaises(PermissionError):
            self.bridge.issue(queue)
        queue.claim.assert_not_called()
    def test_malformed_token_never_opens_database(self):
        grant=self.bridge("postgresql://synthetic.invalid/db")
        grant._db=Mock(side_effect=AssertionError("Must not connect"))
        for token in ("", None, "0"*96, "g"*97, "0"*32+"."+"A"*64):
            with self.subTest(token=token):
                with self.assertRaises(PermissionError):
                    grant.take(token)
        grant._db.assert_not_called()
    def test_empty_queue_does_not_issue_capability(self):
        queue=Mock()
        queue.claim.return_value=None
        self.assertIsNone(self.bridge.issue(queue,approved=True))
        self.assertEqual(queue.claim.call_count,1)
if __name__=="__main__": unittest.main()
