"""Disposable PostgreSQL 18 test for the existing source gate and backup bridge.

This file NEVER accesses production or transfers an encrypted real backup.
It is activated only with a synthetic local PostgreSQL CI DSN, and creates a
new one-off test-only database for each test. All original data stays untouched.
"""
from __future__ import annotations

import os
import shutil
import unittest
import uuid
from urllib.parse import unquote, urlsplit

from scripts.cano_backup_source_gate import APP_SOURCE_PROFILES, require_application_source


@unittest.skipUnless(
    os.environ.get("CANO_CI_RENDER_SOURCE_GATE_DSN"),
    "Requires explicitly configured disposable LOCAL PostgreSQL service",
)
class RenderCanoSourceGatePG18Test(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql

        self.psycopg, self.sql = psycopg, sql
        dsn = os.environ["CANO_CI_RENDER_SOURCE_GATE_DSN"]
        parsed = urlsplit(dsn)
        # Strict fixed CI identity: no remote/networked production DSNs.
        if (
            parsed.scheme != "postgresql"
            or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.port != 5432
            or parsed.path != "/ci_persistence"
            or parsed.username != "ci_user"
            or unquote(parsed.password or "") != "synthetic-ci-only"
        ):
            raise RuntimeError("Synthetic PG18 source gate requires exact local CI identity")

        self.admin_dsn = dsn
        self.database = "ci_cano_gate_" + uuid.uuid4().hex[:14]
        self.admin = psycopg.connect(dsn, autocommit=True)
        self.admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.database))
        )
        self.env = {
            "PGHOST": "127.0.0.1",
            "PGPORT": "5432",
            "PGDATABASE": self.database,
            "PGUSER": "ci_user",
            "PGPASSWORD": "synthetic-ci-only",
        }
        self.bin = shutil.which("psql")
        if not self.bin:
            raise RuntimeError("CI PostgreSQL psql binary missing")

    def tearDown(self):
        if getattr(self, "admin", None) is not None:
            self.admin.execute(
                self.sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    self.sql.Identifier(self.database)
                )
            )
            self.admin.close()

    def _make_tables(self, names):
        with self.psycopg.connect(self.admin_dsn, dbname=self.database) as conn:
            for name in names:
                conn.execute(
                    self.sql.SQL("CREATE TABLE public.{} (id integer PRIMARY KEY)").format(
                        self.sql.Identifier(name)
                    )
                )

    def _first_row(self):
        with self.psycopg.connect(self.admin_dsn, dbname=self.database) as conn:
            conn.execute(
                self.sql.SQL("INSERT INTO public.{} (id) VALUES (1)").format(
                    self.sql.Identifier(APP_SOURCE_PROFILES["full"][0])
                )
            )

    def _check(self):
        return require_application_source(
            self.env, "full",
            expected_host="127.0.0.1",
            expected_database=self.database,
            psql_bin=self.bin,
        )

    def test_01_wrong_or_empty_database_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "application source inventory"):
            self._check()

    def test_02_missing_one_required_table_is_rejected(self):
        self._make_tables(APP_SOURCE_PROFILES["full"][:-1])
        self._first_row()
        with self.assertRaisesRegex(ValueError, "application source inventory"):
            self._check()

    def test_03_correct_tables_but_zero_rows_is_rejected(self):
        self._make_tables(APP_SOURCE_PROFILES["full"])
        with self.assertRaisesRegex(ValueError, "application source inventory"):
            self._check()

    def test_04_complete_populated_synthetic_source_passes(self):
        self._make_tables(APP_SOURCE_PROFILES["full"])
        self._first_row()
        receipt = self._check()
        self.assertEqual(receipt["profile"], "full")
        self.assertEqual(receipt["required_tables_matched"], 9)
        self.assertTrue(receipt["nonempty_table_verified"])
        self.assertNotIn("synthetic-ci-only", str(receipt))


if __name__ == "__main__":
    unittest.main()
