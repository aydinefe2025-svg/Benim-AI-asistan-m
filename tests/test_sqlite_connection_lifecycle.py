"""Connections close promptly, including when a transaction rolls back."""
import tempfile
import unittest
from pathlib import Path

from core.knowledge_store import KnowledgeStore


class ConnectionLifecycleTests(unittest.TestCase):
    def test_connection_closed_and_transaction_rolled_back_after_error(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'knowledge.sqlite3'
            store = KnowledgeStore(db)
            with self.assertRaisesRegex(RuntimeError, 'abort'):
                with store._connection() as conn:
                    conn.execute("INSERT INTO sources(url,title,accessed_at) VALUES(?,?,?)",
                                 ('https://example.org', 'Discarded', '2026-11-02'))
                    raise RuntimeError('abort')
            self.assertEqual(store.list_sources(), [])
            with self.assertRaisesRegex(Exception, 'closed database'):
                conn.execute('SELECT 1')
            moved = db.with_suffix('.moved')
            db.rename(moved)
            self.assertTrue(moved.exists())
