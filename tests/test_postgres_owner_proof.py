import hashlib
import hmac
import unittest

from core.postgres_owner_proof import set_owner_context


class Cursor:
    def __init__(self, row):
        self.row = row
        self.calls = []
    def execute(self, sql, args=None):
        self.calls.append((sql, args))
    def fetchone(self):
        return self.row


class TestOwnerProof(unittest.TestCase):
    def setUp(self):
        self.env = {"CANO_OWNER_PROOF_MODE": "required",
                    "CANO_OWNER_PROOF_KEYS_JSON": '{"agent_task_app":"' + "01"*32 + '"}'}

    def test_legacy_call_unchanged(self):
        cur = Cursor(None)
        set_owner_context(cur, "synthetic-a", environment={})
        self.assertEqual(cur.calls, [("SELECT set_config('cano.owner_key', %s, true)", ("synthetic-a",))])

    def test_proof_binds_role_owner_transaction_backend(self):
        expected = hmac.new(bytes.fromhex("01"*32), b"agent_task_app:synthetic-a:123:456", hashlib.sha256).hexdigest()
        for row in [("agent_task_app", "123", "456"),
                    {"role_name":"agent_task_app","xact_id":"123","backend_pid":"456"}]:
            cur = Cursor(row)
            set_owner_context(cur, "synthetic-a", environment=self.env)
            self.assertEqual(len(cur.calls), 2)
            self.assertEqual(cur.calls[-1][1], ("synthetic-a", expected))

    def test_transaction_changes_signature(self):
        a, b = Cursor(("agent_task_app","123","456")), Cursor(("agent_task_app","124","456"))
        set_owner_context(a, "synthetic-a", environment=self.env)
        set_owner_context(b, "synthetic-a", environment=self.env)
        self.assertNotEqual(a.calls[-1][1][1], b.calls[-1][1][1])

    def test_bad_configuration_fails_before_setting_scope(self):
        for row, env in [(("assistant_owner","123","456"), self.env),
                         (("agent_task_app","123","456"), {"CANO_OWNER_PROOF_MODE":"required"}),
                         (("agent_task_app","123","456"), {"CANO_OWNER_PROOF_MODE":"required","CANO_OWNER_PROOF_KEYS_JSON":"[]"}),
                         (("agent_task_app","123","456"), {"CANO_OWNER_PROOF_MODE":"typo"})]:
            cur = Cursor(row)
            with self.assertRaises(PermissionError):
                set_owner_context(cur, "synthetic-a", environment=env)
            self.assertFalse(any("set_config" in sql for sql, _ in cur.calls))

    def test_ambiguous_scope_rejected(self):
        cur = Cursor(("agent_task_app","123","456"))
        with self.assertRaises(PermissionError):
            set_owner_context(cur, "a:b", environment=self.env)
        self.assertEqual(cur.calls, [])
