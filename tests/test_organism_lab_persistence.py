import base64
import hashlib
import json
import unittest

from core.organism_lab_persistence import OrganismLabStore


class FakeDatabase:
    def __init__(self):
        self.records = {}
        self.connections = 0
        self.owner_filters = []
        self.history_owner_filters = []

    def connect(self, *args, **kwargs):
        self.connections += 1
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
        if "has_table_privilege" in sql:
            self.row = (True, True)
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

    def test_write_is_committed_then_read_back_on_fresh_connection(self):
        db = FakeDatabase()
        store = OrganismLabStore(self.OWNER, "postgresql://test", connect=db.connect)
        raw = b'{"result":"checked"}'
        saved = store.save_verified("campaign", raw)
        self.assertEqual(saved["data"], raw)
        self.assertEqual(saved["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(db.connections, 2)
        self.assertEqual(db.owner_filters, [self.OWNER])

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
