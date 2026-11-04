import unittest

from core.postgres_authorized_queue import PostgresAuthorizedQueue


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
        return {"owns_table": self.owns_tables}


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


class PostgresAuthorizedQueueInitializeTests(unittest.TestCase):
    def _initialize(self, owns_tables):
        queries = []
        queue = PostgresAuthorizedQueue(
            "postgresql://unused",
            owner_key="owner",
            connect=lambda *_args, **_kwargs: _Connection(queries, owns_tables),
        )
        queue.initialize()
        return [query.strip().upper() for query in queries]

    def test_runtime_never_runs_index_ddl_for_shared_or_owned_tables(self):
        for owns_tables in (False, True):
            with self.subTest(owns_tables=owns_tables):
                queries = self._initialize(owns_tables=owns_tables)
                self.assertEqual(
                    sum(query.startswith("CREATE TABLE") for query in queries), 2
                )
                self.assertFalse(any(query.startswith("CREATE INDEX") for query in queries))
                self.assertFalse(any("PG_GET_USERBYID" in query for query in queries))

if __name__ == "__main__":
    unittest.main()
