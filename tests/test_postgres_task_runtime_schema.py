import unittest

from core.postgres_task_store import PostgresTaskStore


class Cursor:
    def __init__(self, sequence_allowed=True):
        self.statements = []
        self.sequence_allowed = sequence_allowed
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, statement, params=None): self.statements.append(statement)
    def fetchone(self): return (self.sequence_allowed,)


class Connection:
    def __init__(self, cursor): self._cursor = cursor
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self._cursor


class PostgresTaskStoreRuntimeSchemaTests(unittest.TestCase):
    def make_store(self, sequence_allowed=True):
        cursor = Cursor(sequence_allowed)
        store = PostgresTaskStore("postgresql://unused", "owner", connect=lambda *a, **k: Connection(cursor))
        return store, cursor

    def test_runtime_schema_check_is_read_only(self):
        store, cursor = self.make_store()
        store.verify_schema()
        self.assertEqual(len(cursor.statements), 4)
        self.assertTrue(all(statement.lstrip().upper().startswith("SELECT") for statement in cursor.statements))
        self.assertTrue(all("LIMIT 0" in statement for statement in cursor.statements[:3]))

    def test_runtime_schema_check_rejects_missing_sequence_privilege(self):
        store, _ = self.make_store(sequence_allowed=False)
        with self.assertRaisesRegex(PermissionError, "sequence USAGE"):
            store.verify_schema()


if __name__ == "__main__":
    unittest.main()
