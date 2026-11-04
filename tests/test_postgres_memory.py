import json
import unittest

from core.postgres_memory import DatabaseNotConfigured, PostgresMemoryStore


class FakeCursor:
    def __init__(self):
        self.statements = []
        self.rows = []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def execute(self, sql, params=None):
        self.statements.append((sql, params))
    def executemany(self, sql, params):
        self.statements.append((sql, list(params)))
    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.c = cursor
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def cursor(self):
        return self.c


class PostgresMemoryTests(unittest.TestCase):
    def setUp(self):
        self.cursor = FakeCursor()
        self.connections = []
        def connect(url, *, connect_timeout):
            self.connections.append((url, connect_timeout))
            return FakeConnection(self.cursor)
        self.store = PostgresMemoryStore("postgresql://example.invalid/test", connect=connect)

    def test_schema_is_private_by_default(self):
        self.store.initialize()
        sql, _ = self.cursor.statements[-1]
        self.assertIn("PRIMARY KEY (owner_key, entry_id)", sql)

    def test_save_uses_parameters_not_interpolation(self):
        entry = {"id": "id-1", "text": "O'Reilly"}
        self.store.save("owner-1", entry)
        sql, rows = self.cursor.statements[-1]
        self.assertNotIn("O'Reilly", sql)
        self.assertEqual(rows[0][0:2], ("owner-1", "id-1"))
        self.assertEqual(json.loads(rows[0][2]), entry)

    def test_list_is_scoped_to_owner(self):
        self.cursor.rows = [(json.dumps({"id": "id-1"}),)]
        self.assertEqual(self.store.list("owner-1"), [{"id": "id-1"}])
        self.assertEqual(self.cursor.statements[-1][1], ("owner-1",))

    def test_save_many_batches_only_owner_scoped_parameterized_entries(self):
        entries = [{"id": "id-1", "text": "first"}, {"id": "id-2", "text": "second"}]
        self.store.save_many("owner-1", entries)
        sql, rows = self.cursor.statements[-1]
        self.assertIn("ON CONFLICT (owner_key, entry_id)", sql)
        self.assertEqual([row[:2] for row in rows], [
            ("owner-1", "id-1"), ("owner-1", "id-2"),
        ])
        self.assertEqual([json.loads(row[2]) for row in rows], entries)

    def test_save_many_validates_all_entries_before_connecting(self):
        with self.assertRaises(ValueError):
            self.store.save_many("owner-1", [
                {"id": "id-1"}, {"text": "missing id"},
            ])
        self.assertEqual(self.connections, [])

    def test_delete_is_scoped_to_owner_and_id(self):
        self.store.delete("owner-1", "id-1")
        self.assertEqual(self.cursor.statements[-1][1], ("owner-1", "id-1"))

    def test_missing_owner_rejected(self):
        with self.assertRaises(ValueError):
            self.store.save("", {"id": "id-1"})
        with self.assertRaises(ValueError):
            self.store.list("")

    def test_missing_url_rejected(self):
        with self.assertRaises(DatabaseNotConfigured):
            PostgresMemoryStore(database_url="", connect=lambda *a, **k: None)


if __name__ == "__main__":
    unittest.main()
