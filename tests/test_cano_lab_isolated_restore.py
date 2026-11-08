"""Regression tests for owner-scoped, isolated Organism Lab v2 recovery."""
import base64
import hashlib
import json
import os
import unittest
from unittest.mock import patch

from core.backup_encryption import encrypt_backup
from core.cano_backup_bundle import create_portable_bundle
from scripts.cano_lab_isolated_restore import restore_lab_archive

OWNER = "oidc_" + "a" * 64
OTHER = "oidc_" + "b" * 64
STAGING_URL = "postgresql://localhost:5432/cano_restore_lab_ci"
PASSWORD = "test-only-long-passphrase"


class Database:
    def __init__(self):
        self.name = "cano_restore_lab_ci"
        self.rows = {}
        self.connect_count = 0
        self.fail_after = None

    def connect(self, url, **kwargs):
        self.connect_count += 1
        assert url == STAGING_URL
        return Connection(self)


class Connection:
    def __init__(self, db):
        self.db = db
        self.pending = []
        self.owner = None

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        if error_type is None:
            for key, payload in self.pending:
                self.db.rows[key] = payload
        self.pending.clear()
        return False

    def cursor(self):
        return Cursor(self)


class Cursor:
    def __init__(self, connection):
        self.conn = connection
        self.row = None
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        sql = " ".join(query.split())
        db = self.conn.db
        if "set_config('cano.owner_key'" in sql:
            self.conn.owner = params[0]
            self.row = (params[0],)
        elif "current_database()" in sql:
            self.row = (db.name,)
        elif "pg_advisory_xact_lock" in sql:
            self.row = ("",)
        elif "SET LOCAL row_security = off" in sql:
            self.row = None
        elif "SELECT COUNT(*)" in sql:
            self.row = (len(db.rows),)
        elif "INSERT INTO public.organism_lab_records" in sql:
            if db.fail_after is not None and len(self.conn.pending) >= db.fail_after:
                raise RuntimeError("synthetic SQL failure")
            owner, collection, identifier, payload = params
            key = (owner, collection, identifier)
            if key in db.rows or key in dict(self.conn.pending):
                raise RuntimeError("duplicate record")
            self.conn.pending.append((key, json.loads(payload)))
        elif "record_id LIKE %s" in sql:
            owner, collection, prefix, limit = params
            self.rows = [(key[2], value, None) for key, value in db.rows.items()
                         if key[:2] == (owner, collection) and key[2].startswith(prefix[:-1])][:limit]
            self.rows.sort(key=lambda row: row[0])
        else:
            raise AssertionError("Unexpected SQL: " + sql)

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def archive_with(records, *, v2=True):
    colony = {name: [] for name in ("agents", "feedback", "reviews", "missions")}
    bundle = create_portable_bundle(
        colony=colony, memories=[], research_tasks=b'{}', authorized_queue=[],
        organism_records=records if v2 else None)
    return encrypt_backup(bundle, PASSWORD)


def record(tick, kind="world"):
    raw = json.dumps({"tick": tick}, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return {"record_id": f"cano-organism-lab-v1-{kind}-{digest}", "kind": kind,
            "sha256": digest, "data_b64": base64.b64encode(raw).decode("ascii")}


class IsolatedLabRestoreTests(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.env = patch.dict(os.environ, {
            "CANO_DATABASE_URL": "postgresql://localhost:5432/assistant_pg",
            "DATABASE_URL": "postgresql://localhost:5432/assistant_pg",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def restore(self, archive, **kwargs):
        return restore_lab_archive(
            archive, PASSWORD, database_url=STAGING_URL, owner_key=OWNER,
            connect=self.db.connect, **kwargs)

    def test_v2_transaction_and_fresh_owner_readback(self):
        expected = [record(1), record(2, "campaign")]
        result = self.restore(archive_with(expected))
        self.assertEqual(result["restored_records"], 2)
        self.assertEqual(result["status"], "ISOLATED_LAB_RESTORED")
        self.assertGreaterEqual(self.db.connect_count, 2)
        self.assertEqual({key[0] for key in self.db.rows}, {OWNER})
        self.assertEqual(len(self.db.rows), 2)
        with self.assertRaisesRegex(ValueError, "not empty"):
            self.restore(archive_with(expected))
        self.assertEqual(len(self.db.rows), 2)

    def test_wrong_key_tamper_and_v1_refuse_before_database_connection(self):
        backup = archive_with([record(3)])
        for blob, password in [(backup, "wrong-test-password"), (backup[:-1] + bytes([backup[-1] ^ 1]), PASSWORD),
                               (archive_with([], v2=False), PASSWORD)]:
            with self.subTest(length=len(blob)):
                with self.assertRaises(ValueError):
                    restore_lab_archive(blob, password, database_url=STAGING_URL,
                                        owner_key=OWNER, connect=self.db.connect)
        self.assertEqual(self.db.connect_count, 0)

    def test_source_alias_or_nonisolated_target_is_rejected_without_connection(self):
        backup = archive_with([record(4)])
        for target in ["postgresql://localhost:5432/assistant_pg",
                       "postgresql://localhost:5432/cano_restore_lab_ci?dbname=assistant_pg"]:
            with self.assertRaises(ValueError):
                restore_lab_archive(backup, PASSWORD, database_url=target,
                                    owner_key=OWNER, connect=self.db.connect)
        with patch.dict(os.environ, {"CANO_DATABASE_URL": STAGING_URL}):
            with self.assertRaises(ValueError):
                self.restore(backup)
        self.assertEqual(self.db.connect_count, 0)

    def test_db_name_mismatch_is_rejected_before_write(self):
        self.db.name = "assistant_pg"
        with self.assertRaisesRegex(ValueError, "target"):
            self.restore(archive_with([record(5)]))
        self.assertEqual(self.db.rows, {})

    def test_sql_failure_rolls_back_all_rows(self):
        self.db.fail_after = 1
        with self.assertRaisesRegex(RuntimeError, "synthetic SQL failure"):
            self.restore(archive_with([record(6), record(7)]))
        self.assertEqual(self.db.rows, {})

    def test_other_account_is_never_read_or_mutated(self):
        # A staging table containing another owner's row is NOT an empty
        # database. Recovery must refuse rather than rely on owner RLS visibility.
        other = record(8)
        self.db.rows[(OTHER, "simulation", other["record_id"])] = {
            "format": 1, "sha256": other["sha256"], "data_b64": other["data_b64"]}
        with self.assertRaisesRegex(ValueError, "not empty"):
            self.restore(archive_with([record(9)]))
        self.assertEqual(len(self.db.rows), 1)


if __name__ == "__main__":
    unittest.main()
