import base64
import hashlib
import json
import unittest

from core.organism_lab_persistence import OrganismLabPermissionsError, OrganismLabStore


class FakeDatabase:
    def __init__(self):
        self.records = {}
        self.connections = 0
        self.owner_filters = []
        self.history_owner_filters = []
        self.configured_owners = []
        self.can_select = True
        self.can_insert = True
        self.rls_active = True
        self.rls_bypass = False
        self.policy_member = True
        self.runtime_select_policy = False
        self.runtime_insert_policy = False
        self.fail_second_connection_with = None

    def connect(self, *args, **kwargs):
        self.connections += 1
        if self.connections == 2 and self.fail_second_connection_with is not None:
            raise self.fail_second_connection_with
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, database):
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return FakeCursor(self.database)


class FakeCursor:
    def __init__(self, database):
        self.database = database
        self.row = None
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if "set_config('cano.owner_key'" in sql:
            self.database.configured_owners.append(params[0])
            self.row = (params[0],)
        elif "has_table_privilege" in sql:
            self.row = ("assistant_test", self.database.can_select, self.database.can_insert)
        elif "pg_policies" in sql:
            self.row = (self.database.rls_active,
                        self.database.rls_bypass,
                        self.database.policy_member or (
                            self.database.runtime_select_policy
                            and self.database.runtime_insert_policy))
        elif "pg_has_role" in sql:
            self.row = (self.database.rls_active,
                        self.database.rls_bypass,
                        self.database.policy_member)
        elif sql.lstrip().startswith("INSERT INTO"):
            owner, collection, record_id, encoded = params
            self.database.records.setdefault(
                (owner, collection, record_id), json.loads(encoded))
        elif "WHERE owner_key=%s AND collection=%s AND record_id=%s" in sql:
            owner, collection, record_id = params
            self.database.owner_filters.append(owner)
            payload = self.database.records.get((owner, collection, record_id))
            self.row = (payload, "2026-11-06T12:00:00Z") if payload else None
        elif "record_id LIKE %s" in sql:
            owner, collection, prefix, limit = params
            self.database.owner_filters.append(owner)
            self.database.history_owner_filters.append(owner)
            found = [
                (record_id, payload, "2026-11-06T12:00:00Z")
                for (record_owner, record_collection, record_id), payload
                in self.database.records.items()
                if record_owner == owner and record_collection == collection
                and record_id.startswith(prefix[:-1])
            ]
            self.rows = found[:limit]
        else:
            self.row = None

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class OrganismLabPersistenceTests(unittest.TestCase):
    OWNER = "oidc_" + "a" * 64

    def test_preflight_checks_runtime_grants_without_table_data(self):
        db = FakeDatabase()
        store = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        self.assertEqual(store.verify_schema(), "assistant_test")
        db.can_select = False
        with self.assertRaises(OrganismLabPermissionsError) as caught:
            store.verify_schema()
        self.assertEqual(caught.exception.role_name, "assistant_test")
        self.assertFalse(caught.exception.can_select)
        self.assertTrue(caught.exception.can_insert)
        self.assertNotIn("assistant_test", str(caught.exception))

    def test_preflight_rejects_grant_only_role_when_rls_blocks_the_record(self):
        # Live Neon can grant SELECT+INSERT but omit a matching RLS policy.
        from core import organism_lab_persistence
        db = FakeDatabase()
        db.policy_member = False
        store = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        self.assertTrue(db.can_insert)
        error_type = getattr(organism_lab_persistence, "OrganismLabRlsPolicyError", None)
        self.assertIsNotNone(error_type)
        with self.assertRaises(error_type) as caught:
            store.verify_schema()
        self.assertEqual(caught.exception.role_name, "assistant_test")
        self.assertNotIn("assistant_test", str(caught.exception))
        self.assertEqual(db.records, {})

    def test_live_neon_runtime_role_succeeds_only_with_both_owner_scoped_rls_policies(self):
        # The production CANO_DATABASE_URL authenticates as cano_runtime_rw.
        # Neon now has its *own* owner-bound SELECT and INSERT policies for
        # that role, rather than membership in cano_snapshot_app.
        db = FakeDatabase()
        db.policy_member = False
        db.runtime_select_policy = True
        db.runtime_insert_policy = True
        store = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        self.assertEqual(store.verify_schema(), "assistant_test")
        self.assertEqual(db.records, {})

    def test_neon_runtime_role_still_denied_when_either_policy_missing(self):
        from core.organism_lab_persistence import OrganismLabRlsPolicyError
        for has_select, has_insert in ((False, False), (True, False), (False, True)):
            with self.subTest(select=has_select, insert=has_insert):
                db = FakeDatabase()
                db.policy_member = False
                db.runtime_select_policy = has_select
                db.runtime_insert_policy = has_insert
                store = OrganismLabStore(self.OWNER, "postgresql://test",
                                         connect=db.connect)
                with self.assertRaises(OrganismLabRlsPolicyError):
                    store.verify_schema()
                self.assertEqual(db.records, {})

    def test_transient_readback_connection_failure_retries_once_without_rewriting(self):
        db = FakeDatabase()
        db.fail_second_connection_with = ConnectionError("PRIVATE transient connection")
        store = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        outcome = store.save_verified("world", b'{"steps":5}')
        self.assertEqual(outcome["data"], b'{"steps":5}')
        self.assertEqual(db.connections, 3)
        self.assertEqual(len(db.records), 1)

    def test_nontransient_readback_failure_never_retries(self):
        db = FakeDatabase()
        db.fail_second_connection_with = PermissionError("PRIVATE access denied")
        store = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        with self.assertRaises(PermissionError):
            store.save_verified("world", b'{"steps":5}')
        self.assertEqual(db.connections, 2)

    def test_write_is_committed_then_read_back_on_fresh_connection(self):
        db = FakeDatabase()
        store = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        raw = b'{"result":"checked"}'
        saved = store.save_verified("campaign", raw)
        self.assertEqual(saved["data"], raw)
        self.assertEqual(saved["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(db.connections, 2)
        self.assertEqual(db.owner_filters, [self.OWNER])
        self.assertEqual(db.configured_owners, [self.OWNER, self.OWNER])

    def test_content_addressing_makes_same_run_idempotent(self):
        db = FakeDatabase()
        store = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        first = store.save_verified("world", b'{"steps":4}')
        second = store.save_verified("world", b'{"steps":4}')
        self.assertEqual(first["record_id"], second["record_id"])
        self.assertEqual(len(db.records), 1)

    def test_history_is_scoped_to_authenticated_owner(self):
        db = FakeDatabase()
        first = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        other = OrganismLabStore("oidc_" + "b" * 64, "postgresql://test", connect=db.connect)
        first.save_verified("world", b'{"owner":"first"}')
        other.save_verified("world", b'{"owner":"other"}')
        records = first.list_recent()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["document"], {"owner": "first"})
        self.assertEqual(db.history_owner_filters, [self.OWNER])

    def test_backup_exports_all_owner_experiments_without_history_truncation(self):
        db = FakeDatabase()
        mine = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        other = OrganismLabStore("oidc_" + "b" * 64, "postgresql://test",
                                 connect=db.connect)
        for i in range(24):
            mine.save_verified("world", json.dumps({"tick": i}).encode("utf-8"))
        other.save_verified("world", b'{"private":"other-owner"}')
        exported = mine.export_for_backup()
        self.assertEqual(len(exported), 24)
        self.assertEqual(len({item["record_id"] for item in exported}), 24)
        self.assertEqual(db.history_owner_filters[-1], self.OWNER)
        self.assertEqual({item["kind"] for item in exported}, {"world"})
        for item in exported:
            raw = base64.b64decode(item["data_b64"], validate=True)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])
            self.assertNotIn("owner_key", item)
            self.assertNotIn(b"other-owner", raw)

    def test_backup_must_fail_instead_of_silently_truncating_experiments(self):
        db = FakeDatabase()
        mine = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        for i in range(1001):
            data = json.dumps({"tick": i}).encode("utf-8")
            digest = hashlib.sha256(data).hexdigest()
            rec_id = f"cano-organism-lab-v1-world-{digest}"
            db.records[(self.OWNER, "simulation", rec_id)] = {
                "format": 1, "sha256": digest,
                "data_b64": base64.b64encode(data).decode("ascii")
            }
        with self.assertRaisesRegex(ValueError, "limit"):
            mine.export_for_backup()

    def test_corrupt_history_fails_integrity_check(self):
        db = FakeDatabase()
        store = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        record = store.save_verified("world", b'{"steps":4}')
        key = (self.OWNER, "simulation", record["record_id"])
        db.records[key]["data_b64"] = base64.b64encode(b'{"steps":5}').decode("ascii")
        with self.assertRaisesRegex(ValueError, "integrity"):
            store.list_recent()

    def test_invalid_identity_kind_or_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            OrganismLabStore("not-an-owner", "postgresql://test", connect=lambda *a, **k: None)
        db = FakeDatabase()
        store = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        with self.assertRaises(ValueError):
            store.save_verified("other", b"{}")
        with self.assertRaises(ValueError):
            store.save_verified("world", b"x" * (store.MAX_RECORD_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
