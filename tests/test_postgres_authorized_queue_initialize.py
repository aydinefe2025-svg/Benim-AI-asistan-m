import unittest

from core.postgres_authorized_queue import PostgresAuthorizedQueue


class _Cursor:
    def __init__(self, queries, privileges):
        self.queries = queries
        self.privileges = privileges

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.queries.append(sql)

    def fetchone(self):
        return self.privileges


class _Connection:
    def __init__(self, queries, privileges):
        self.queries = queries
        self.privileges = privileges

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return _Cursor(self.queries, self.privileges)


class PostgresAuthorizedQueueSchemaTests(unittest.TestCase):
    def _verify(self, privileges):
        queries = []
        queue = PostgresAuthorizedQueue(
            "postgresql://unused",
            owner_key="owner",
            connect=lambda *_args, **_kwargs: _Connection(queries, privileges),
        )
        queue.verify_schema()
        return [query.strip().upper() for query in queries]

    @staticmethod
    def _all_privileges():
        return {
            "jobs_select": True,
            "jobs_insert": True,
            "jobs_update": True,
            "events_select": True,
            "events_insert": True,
            "events_seq_usage": True,
        }

    def test_runtime_schema_verification_is_read_only(self):
        queries = self._verify(self._all_privileges())
        self.assertEqual(len(queries), 3)
        self.assertTrue(all(query.startswith("SELECT") for query in queries))
        self.assertTrue(all("LIMIT 0" in query for query in queries[:2]))
        self.assertIn("HAS_SEQUENCE_PRIVILEGE", queries[-1])

    def test_missing_runtime_privilege_fails_closed(self):
        privileges = self._all_privileges()
        privileges["events_seq_usage"] = False
        with self.assertRaisesRegex(PermissionError, "privileges"):
            self._verify(privileges)


if __name__ == "__main__":
    unittest.main()
