import unittest

from core.postgres_memory import PostgresMemoryStore


class Cursor:
    def __init__(self): self.statements = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, statement, params=None): self.statements.append(statement)


class Connection:
    def __init__(self, cursor): self._cursor = cursor
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self._cursor


class PostgresMemoryRuntimeSchemaTests(unittest.TestCase):
    def test_runtime_schema_check_is_read_only(self):
        cursor = Cursor()
        store = PostgresMemoryStore("postgresql://unused", connect=lambda *a, **k: Connection(cursor))
        store.verify_schema()
        self.assertEqual(len(cursor.statements), 1)
        statement = cursor.statements[0].lstrip().upper()
        self.assertTrue(statement.startswith("SELECT"))
        self.assertIn("PRIVATE_MEMORY_ENTRIES", statement)
        self.assertIn("LIMIT 0", statement)


if __name__ == "__main__":
    unittest.main()
