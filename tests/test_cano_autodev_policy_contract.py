"""Prevent activation of the optional CANO worker under drifted or broad Neon RLS policies.

No actual database reads or credentials: the fake cursor returns catalog metadata.
Tests expect an independent startup RLS contract check, not merely relrowsecurity.
"""
import unittest
from scripts.cano_autodev_worker import NeonJobStore


OWNER = "oidc_" + "a"*64
OTHER = "oidc_" + "b"*64


def correct_policies(owner=OWNER):
    predicate = "(owner_key = '" + owner + "'::text)"
    return [
        ("cano_autodev_worker_select", "SELECT", ["cano_autodev_worker"],
         "PERMISSIVE", predicate, None),
        ("cano_autodev_worker_update", "UPDATE", ["cano_autodev_worker"],
         "PERMISSIVE",
         "(" + predicate + " AND (status = ANY (ARRAY['queued'::text, 'running'::text])))",
         "(" + predicate + " AND (status = ANY (ARRAY['running'::text, 'pr_open'::text, 'blocked'::text])))"),
        ("cano_code_jobs_web_read", "SELECT", ["agent_task_app"],
         "PERMISSIVE", "(owner_key = 'web'::text)", None),
    ]


class Cursor:
    def __init__(self, policies):
        self.policies = policies
        self.sql = ""
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params=None): self.sql = sql
    def fetchone(self):
        if "FROM pg_roles" in self.sql:
            return ("cano_autodev_worker", False, False)
        if "FROM pg_class" in self.sql:
            return (True, False)
        raise AssertionError("unexpected SQL")
    def fetchall(self):
        if "FROM pg_policies" in self.sql:
            return self.policies
        raise AssertionError("unexpected SQL")


class Connection:
    def __init__(self, cursor): self.cursor_obj = cursor
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self.cursor_obj


def store_with(policies):
    store = NeonJobStore.__new__(NeonJobStore)
    store.owner_key = OWNER
    cursor = Cursor(policies)
    store._connect = lambda: Connection(cursor)
    return store


class Worker'sRLSStartupContract(unittest.TestCase):
    def test_exact_existing_owner_scoped_policy_contract_permitted(self):
        store_with(correct_policies()).verify_worker_role()

    def test_other_owner_policy_must_block_before_any_claim(self):
        with self.assertRaisesRegex(PermissionError, "RLS"):
            store_with(correct_policies(OTHER)).verify_worker_role()

    def test_policy_removed_must_block_before_any_claim(self):
        with self.assertRaisesRegex(PermissionError, "RLS"):
            store_with(correct_policies()[:1]).verify_worker_role()

    def test_public_role_policy_must_block_before_any_claim(self):
        policies=correct_policies()+[("unexpected", "SELECT", ["public"],
                                     "PERMISSIVE", "true", None)]
        with self.assertRaisesRegex(PermissionError, "RLS"):
            store_with(policies).verify_worker_role()

    def test_new_broad_permissive_policy_must_block_before_any_claim(self):
        policies=correct_policies()+[("worker_all", "ALL", ["cano_autodev_worker"],
                                     "PERMISSIVE", "true", "true")]
        with self.assertRaisesRegex(PermissionError, "RLS"):
            store_with(policies).verify_worker_role()

    def test_update_can_not_expand_to_other_statuses(self):
        policies=correct_policies()
        name, cmd, roles, permissive, using, check=policies[1]
        policies[1]=(name, cmd, roles, permissive, "true", check)
        with self.assertRaisesRegex(PermissionError, "RLS"):
            store_with(policies).verify_worker_role()

    def test_update_can_not_use_unlimited_with_check(self):
        policies=correct_policies()
        name, cmd, roles, permissive, using, check=policies[1]
        policies[1]=(name, cmd, roles, permissive, using, "true")
        with self.assertRaisesRegex(PermissionError, "RLS"):
            store_with(policies).verify_worker_role()


if __name__ == "__main__":
    unittest.main()
