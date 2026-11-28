import base64
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from organism_lab.persistent_store import (
    PersistenceConflict, PersistenceNotConfigured, PostgresArchive, authenticated_owner_key,
    pack_directory, restore_snapshot_json, snapshot_json, unpack_directory,
)


class PersistentStoreTests(unittest.TestCase):
    def test_verified_oidc_identity_is_stably_hmac_scoped(self):
        user = {"is_logged_in": True, "email": "owner@example.com", "email_verified": True,
                "iss": "https://accounts.google.com", "sub": "opaque-subject"}
        first = authenticated_owner_key(user, allowed_email="OWNER@example.com", secret="x" * 32)
        self.assertEqual(len(first), 64)
        self.assertEqual(first, authenticated_owner_key(user, allowed_email="owner@example.com", secret="x" * 32))
        self.assertNotEqual(first, authenticated_owner_key(user, allowed_email="owner@example.com", secret="y" * 32))
        user["email_verified"] = False
        with self.assertRaises(PermissionError):
            authenticated_owner_key(user, allowed_email="owner@example.com", secret="x" * 32)

    def test_only_verified_configured_owner_is_accepted(self):
        user = {"is_logged_in": True, "email": "other@example.com", "email_verified": True,
                "iss": "https://id.example", "sub": "user-1"}
        with self.assertRaises(PermissionError):
            authenticated_owner_key(user, allowed_email="owner@example.com", secret="x" * 32)

    def test_pack_unpack_round_trip_and_integrity_envelope(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            Path(source, "nested").mkdir()
            Path(source, "nested", "report.json").write_text('{"result": 4}', encoding="utf-8")
            data = pack_directory(source)
            self.assertEqual(data, pack_directory(source))
            envelope = snapshot_json(data)
            self.assertEqual(envelope["sha256"], hashlib.sha256(data).hexdigest())
            restore_snapshot_json(envelope, target)
            self.assertEqual(Path(target, "nested", "report.json").read_text(encoding="utf-8"), '{"result": 4}')

    def test_invalid_archive_path_is_rejected(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo("../escape.txt")
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
        with tempfile.TemporaryDirectory() as target:
            with self.assertRaises(ValueError):
                unpack_directory(buffer.getvalue(), target)
            self.assertFalse(Path(target).parent.joinpath("escape.txt").exists())

    def test_database_connection_is_required(self):
        with self.assertRaises(PersistenceNotConfigured):
            PostgresArchive("a" * 64, database_url="", connect=lambda *a, **k: None)

    def test_corrupt_persisted_snapshot_fails_integrity_check(self):
        payload = {"data_b64": base64.b64encode(b"changed").decode("ascii"), "sha256": "0" * 64}
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, *args): pass
            def fetchone(self): return (json.dumps(payload),)
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return Cursor()
        store = PostgresArchive("a" * 64, "postgresql://private", connect=lambda *a, **k: Connection())
        with self.assertRaisesRegex(ValueError, "integrity"):
            store.load()

    def test_archive_conflict_is_fail_closed(self):
        statements = []
        class Cursor:
            def __init__(self): self.row = None
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params):
                statements.append((sql, params))
                if "ON CONFLICT (owner_key" in sql: self.row = None
            def fetchone(self): return self.row
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return Cursor()
        store = PostgresArchive("a" * 64, "postgresql://private", connect=lambda *a, **k: Connection())
        with self.assertRaises(PersistenceConflict):
            store.save(b"next", expected_digest="stale")
        self.assertIn("WHERE public.organism_lab_records.payload->>'sha256'=%s", next(sql for sql, _ in statements if "ON CONFLICT (owner_key" in sql))



class ArchiveScopeTests(unittest.TestCase):
    def test_legacy_scope_is_set_before_archive_read(self):
        from unittest.mock import patch
        calls = []
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params=None): calls.append((sql, params))
            def fetchone(self): return None
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return Cursor()
        with patch.dict("os.environ", {"CANO_OWNER_PROOF_MODE":"off"}):
            store = PostgresArchive("a"*64, "postgresql://test", connect=lambda *a, **k: Connection())
            self.assertEqual(store.load(), (None, None))
        self.assertIn("set_config('organism.owner_key'", calls[0][0])
        self.assertEqual(calls[0][1], ("a"*64,))
    def test_required_mode_rejects_missing_key_before_archive_read(self):
        from unittest.mock import patch
        calls = []
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params=None): calls.append((sql, params))
            def fetchone(self): return ("cano_snapshot_app", "123", "456") if "pg_current_xact_id()" in calls[-1][0] else None
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return Cursor()
        with patch.dict("os.environ", {"CANO_OWNER_PROOF_MODE":"required",
                                        "CANO_OWNER_PROOF_KEYS_JSON":"{}"}):
            store = PostgresArchive("a"*64, "postgresql://test", connect=lambda *a, **k: Connection())
            with self.assertRaises(PermissionError):
                store.load()
        self.assertFalse(any("SELECT payload FROM" in sql for sql, _ in calls))


    def test_required_mode_checks_database_verifier_before_loading(self):
        from unittest.mock import patch
        for verified in ("a"*64, None):
            calls = []
            class Cursor:
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def execute(self, sql, params=None): calls.append((sql, params))
                def fetchone(self):
                    sql = calls[-1][0]
                    if "pg_current_xact_id()" in sql: return ("cano_snapshot_app", "123", "456")
                    if "verified_owner()" in sql: return (verified,)
                    return None
            class Connection:
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def cursor(self): return Cursor()
            with patch.dict("os.environ", {"CANO_OWNER_PROOF_MODE":"required",
                                            "CANO_OWNER_PROOF_KEYS_JSON":json.dumps({"cano_snapshot_app":"ab"*32})}):
                store = PostgresArchive("a"*64, "postgresql://test", connect=lambda *a, **k: Connection())
                if verified is None:
                    with self.assertRaises(PermissionError): store.load()
                    self.assertFalse(any("SELECT payload FROM" in sql for sql, _ in calls))
                else:
                    self.assertEqual(store.load(), (None, None))
                    self.assertIn("cano.owner_proof", calls[1][0])
                    self.assertIn("organism.owner_key", calls[3][0])


if __name__ == "__main__":
    unittest.main()

