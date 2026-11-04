import unittest

from core.postgres_task_store import PostgresTaskStore


class _Cursor:
    def __init__(self, queries, owns_tables):
        self.queries = queries
        self.owns_tables = owns_tables

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.queries.append(sql)

    def fetchone(self):
        return (self.owns_tables,)


class _Connection:
    def __init__(self, queries, owns_tables):
        self.queries = queries
        self.owns_tables = owns_tables

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return _Cursor(self.queries, self.owns_tables)


class PostgresTaskStoreInitializeTests(unittest.TestCase):
    def _initialize(self, owns_tables):
        queries = []
        store = PostgresTaskStore(
            "postgresql://unused",
            owner_key="owner",
            connect=lambda *_args, **_kwargs: _Connection(queries, owns_tables),
        )
        store.initialize()
        return [query.upper().lstrip() for query in queries]

    def test_shared_migration_owned_tables_skip_index_ddl(self):
        queries = self._initialize(owns_tables=False)
        self.assertEqual(sum(query.startswith("CREATE TABLE") for query in queries), 3)
        self.assertFalse(any(query.startswith("CREATE INDEX") for query in queries))
        self.assertEqual(sum("PG_GET_USERBYID" in query for query in queries), 2)

    def test_runtime_owned_tables_create_indexes(self):
        queries = self._initialize(owns_tables=True)
        self.assertEqual(sum(query.startswith("CREATE INDEX") for query in queries), 2)


if __name__ == "__main__":
    unittest.main()
