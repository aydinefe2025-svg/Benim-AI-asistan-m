"""Fail-closed, source-to-restored-PostgreSQL readback contract.

These tests run WITHOUT network, credentials, SQL writes or local databases.
"""
from __future__ import annotations

from hashlib import sha256
import re
import unittest
from unittest.mock import patch
import os

from scripts.cano_dr_compare import TABLES, audit_application_restore

SOURCE = "postgresql://localhost:5432/assistant_pg"
TARGET = "postgresql://localhost:5432/cano_restore_readback"
PAYLOAD = "sensitive private content not to be printed"


class Connection:
    def __init__(self, database_name, rows, missing_tables=()):
        self.name = database_name
        self.rows = rows
        self.missing_tables = set(missing_tables)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return Cursor(self)


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.results = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params=None):
        query = " ".join(statement.split())
        self.connection.statements.append(query)
        if query.startswith("SET TRANSACTION") or query.startswith("SET LOCAL"):
            self.results = []
        elif "current_database()" in query:
            self.results = [(self.connection.name,)]
        elif "information_schema.columns" in query:
            self.results = [
                (t, 1, "payload", "jsonb", "NO", "")
                for t in TABLES if t not in self.connection.missing_tables
            ]
        elif "FROM pg_constraint" in query:
            self.results = []
        elif "FROM pg_indexes" in query:
            self.results = []
        elif "FROM pg_policies" in query:
            self.results = []
        elif "FROM pg_class" in query:
            self.results = [(t, False, False) for t in TABLES
                            if t not in self.connection.missing_tables]
        elif "AS row_sha" in query:
            matched = re.search(r"FROM public\.([a-z_]+) AS r", query)
            if not matched:
                raise AssertionError("Expected allowlisted table query")
            table = matched.group(1)
            self.results = sorted((sha256(x.encode()).hexdigest(),)
                                  for x in self.connection.rows.get(table, []))
        else:
            raise AssertionError("Unexpected SQL statement: " + query)

    def fetchone(self):
        result = self.fetchmany(1)
        return result[0] if result else None

    def fetchall(self):
        result = self.results
        self.results = []
        return result

    def fetchmany(self, size=512):
        result, self.results = self.results[:size], self.results[size:]
        return result


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.source_rows = {table: ["synthetic-" + table] for table in TABLES}
        self.target_rows = {table: list(v) for table, v in self.source_rows.items()}
        self.source = Connection("assistant_pg", self.source_rows)
        self.target = Connection("cano_restore_readback", self.target_rows)
        self.calls = []
        self.environ = patch.dict(os.environ, {
            "CANO_DATABASE_URL": SOURCE,
            "DATABASE_URL": SOURCE,
        })
        self.environ.start()
        self.addCleanup(self.environ.stop)

    def connect(self, url, **kwargs):
        self.calls.append(url)
        return self.source if url == SOURCE else self.target if url == TARGET else None

    def test_same_data_needs_positive_two_connection_readback(self):
        result = audit_application_restore(SOURCE, TARGET, connect=self.connect)
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["verified_tables"], 9)
        self.assertEqual(result["rows_source"], 9)
        self.assertEqual(result["rows_target"], 9)
        self.assertEqual(self.calls, [SOURCE, TARGET])
        self.assertTrue(self.source.statements[0].startswith("SET TRANSACTION"))
        self.assertTrue(self.target.statements[0].startswith("SET TRANSACTION"))
        self.assertTrue(all(not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE)\b", sql)
                            for sql in self.source.statements+self.target.statements))

    def test_same_row_count_but_changed_organism_payload_is_detected(self):
        self.target_rows["organism_lab_records"] = [PAYLOAD]
        result = audit_application_restore(SOURCE, TARGET, connect=self.connect)
        self.assertEqual(result["status"], "DIFFERENT")
        self.assertIn("organism_lab_records", result["mismatched_tables"])
        self.assertEqual(result["rows_source"], result["rows_target"])
        self.assertNotIn(PAYLOAD, str(result))

    def test_same_connection_target_is_rejected_before_access(self):
        with self.assertRaises(ValueError):
            audit_application_restore(SOURCE, SOURCE, connect=self.connect)
        self.assertEqual(self.calls, [])

    def test_wrong_target_name_is_rejected_before_access(self):
        with self.assertRaises(ValueError):
            audit_application_restore(SOURCE, "postgresql://localhost:5432/production_db", connect=self.connect)
        self.assertEqual(self.calls, [])

    def test_missing_table_cannot_be_certified(self):
        self.target.missing_tables.add("private_memory_entries")
        with self.assertRaises(ValueError):
            audit_application_restore(SOURCE, TARGET, connect=self.connect)

    def test_database_name_mismatch_blocks_claim(self):
        self.target.name = "other_database"
        with self.assertRaises(ValueError):
            audit_application_restore(SOURCE, TARGET, connect=self.connect)


if __name__ == "__main__":
    unittest.main()
