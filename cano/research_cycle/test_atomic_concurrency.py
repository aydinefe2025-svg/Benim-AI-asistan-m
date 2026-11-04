"""Regression tests for concurrent workers and evidence ledger completeness."""
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import atomic_batch
import feedback_loop


class AtomicConcurrencyTests(unittest.TestCase):
    def test_simultaneous_same_record_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src, db = root / 'one.jsonl', root / 'findings.sqlite3'
            src.write_text(json.dumps({'kind': 'observation', 'title': 'same', 'source': 'test', 'evidence': 'e'}) + '\n')
            c = feedback_loop.connect(db)
            c.close()
            barrier = threading.Barrier(2)
            original = feedback_loop.validate

            def validate_at_same_time(item):
                barrier.wait(timeout=8)
                return original(item)

            with patch.object(feedback_loop, 'validate', side_effect=validate_at_same_time):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    a = pool.submit(atomic_batch.run, src, db)
                    b = pool.submit(atomic_batch.run, src, db)
                    results = (a.result(timeout=15), b.result(timeout=15))
            self.assertEqual(sum(r['inserted'] for r in results), 1)
            self.assertEqual(sum(r['already_processed'] for r in results), 1)
            self.assertEqual(atomic_batch.audit(db)['checked'], 1)
            self.assertTrue(atomic_batch.audit(db)['ok'])

    def test_receipt_lookup_is_indexed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src, db = root / 'one.jsonl', root / 'findings.sqlite3'
            src.write_text(json.dumps({'kind': 'observation', 'title': 'one', 'source': 'test', 'evidence': 'e'}) + '\n')
            atomic_batch.run(src, db)
            c = sqlite3.connect(db)
            try:
                indexes = [row[1] for row in c.execute('PRAGMA index_list(receipts)')]
            finally:
                c.close()
            self.assertIn('ix_receipts_detail_status', indexes)

    def test_orphan_finding_fails_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src, db = root / 'one.jsonl', root / 'findings.sqlite3'
            src.write_text(json.dumps({'kind': 'observation', 'title': 'record', 'source': 'test', 'evidence': 'e'}) + '\n')
            atomic_batch.run(src, db)
            c = sqlite3.connect(db)
            try:
                c.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?)", ('0' * 64, 'observation', 'orphan', 'test', 'e', 'pending_review', 1))
                c.commit()
            finally:
                c.close()
            self.assertFalse(atomic_batch.audit(db)['ok'])


if __name__ == '__main__':
    unittest.main()
