"""Owner-context regression: a colony read must bind the authenticated tenant
inside the same PostgreSQL transaction, before accessing any private payload.
This is test-only and uses a fake connection: no real user DB or secrets.
"""
import unittest
from core.colony_postgres import ColonySnapshotStore


class TraceCursor:
    def __init__(self, trace):
        self.trace = trace
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, statement, params=None):
        self.trace.append((" ".join(statement.split()), params))
    def fetchone(self):
        return None


class TraceConnection:
    def __init__(self, trace):
        self.trace = trace
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def cursor(self):
        return TraceCursor(self.trace)


class ColonyRLSOwnerContextTest(unittest.TestCase):
    def test_load_binds_owner_context_inside_transaction_before_read(self):
        trace = []
        store = ColonySnapshotStore(
            "postgresql://never-used",
            connect=lambda *args, **kwargs: TraceConnection(trace))
        self.assertIsNone(store.load("tenant-alpha"))
        self.assertGreaterEqual(len(trace), 2)
        self.assertEqual(trace[0], (
            "SELECT set_config('cano.owner_key', %s, true)", ("tenant-alpha",)))
        self.assertIn("FROM private_colony_snapshots", trace[1][0])
        self.assertEqual(trace[1][1], ("tenant-alpha",))


if __name__ == "__main__":
    unittest.main()
