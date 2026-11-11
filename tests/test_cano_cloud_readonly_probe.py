"""Offline synthetic regressions: no real DB connections or secrets."""
import unittest
from scripts.cano_cloud_readonly_probe import blocked, probe, serve

DB = "research_library_persistent_db"
HOST = "dpg-dbkfp5bm8hqs73bba7u0-a"
URL = "postgresql://test:placeholder@" + HOST + ".frankfurt-postgres.render.com/" + DB
ENV = {"CANO_RENDER_INTERNAL_URL": URL,
       "CANO_REQUIRED_RENDER_DATABASE": DB,
       "CANO_REQUIRED_RENDER_HOST_PREFIX": HOST}


class FakeDB:
    def __init__(self, row):
        self.row = row
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, sql):
        self.queries.append(sql)
        if any(word in sql.upper() for word in (" FROM ", "INSERT ", "UPDATE ", "DELETE ")):
            raise AssertionError("Not a metadata-only SELECT")
        return self

    def fetchone(self):
        return self.row


class Tests(unittest.TestCase):
    def test_empty_config_no_network(self):
        self.assertEqual("not_configured",
                         probe({}, connect=lambda *a, **k: self.fail("connected"))["status"])

    def test_mismatched_database_no_network(self):
        self.assertEqual("identity_mismatch",
                         probe({**ENV, "CANO_REQUIRED_RENDER_DATABASE": "different"},
                               connect=lambda *a, **k: self.fail("connected"))["status"])

    def test_neon_host_no_network(self):
        self.assertEqual("identity_mismatch",
                         probe({**ENV, "CANO_RENDER_INTERNAL_URL":
                               "postgresql://test:placeholder@neon.tech/" + DB},
                               connect=lambda *a, **k: self.fail("connected"))["status"])

    def test_good_pg18_readonly_metadata_only(self):
        db = FakeDB((DB, "180006", "on"))
        calls = []
        def connect(uri, *, connect_timeout, options):
            calls.append((uri, connect_timeout, options))
            return db
        result = probe(ENV, connect)
        self.assertTrue(result["internal_readonly_verified"])
        self.assertFalse(result["real_backup_created"])
        self.assertFalse(result["offsite_verified"])
        self.assertEqual(0, result["source_rows_read"])
        self.assertEqual(1, len(db.queries))
        self.assertIn("current_database()", db.queries[0])
        self.assertEqual(5, calls[0][1])
        self.assertIn("default_transaction_read_only=on", calls[0][2])

    def test_pg17_rejected(self):
        self.assertEqual("server_identity_unverified",
                         probe(ENV, connect=lambda *a, **k:
                               FakeDB((DB, "170014", "on")))["status"])

    def test_writable_connection_rejected(self):
        self.assertEqual("server_identity_unverified",
                         probe(ENV, connect=lambda *a, **k:
                               FakeDB((DB, "180006", "off")))["status"])

    def test_exception_redacted(self):
        def bad(*a, **k):
            raise RuntimeError("SUPER_SECRET_DATABASE_PASSWORD")
        result = probe(ENV, connect=bad)
        self.assertEqual("connection_unverified", result["status"])
        self.assertNotIn("SUPER_SECRET", repr(result))
        self.assertNotIn("placeholder", repr(result))

    def test_invalid_port(self):
        for val in (0, -1, 65536, "string"):
            with self.subTest(port=val), self.assertRaises(ValueError):
                serve(blocked(), val)


if __name__ == "__main__":
    unittest.main()
