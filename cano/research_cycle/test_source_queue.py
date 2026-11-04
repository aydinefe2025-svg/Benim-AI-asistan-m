import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from source_queue import validate_record, import_records, import_file

class TestSourceQueue(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE findings (digest TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, source TEXT NOT NULL, evidence TEXT NOT NULL, status TEXT NOT NULL, created INTEGER NOT NULL)')
        self.record={'title':'Example paper','url':'https://doi.org/10.1234/example','summary':'Metadata only',
                     'published':'2026-01-01','source_sha256':'a'*64}
    def tearDown(self):self.db.close()
    def test_valid(self):self.assertEqual(validate_record(self.record)['source'],self.record['url'])
    def test_reject_http(self):
        x=dict(self.record,url='http://doi.org/a')
        with self.assertRaises(ValueError):validate_record(x)
    def test_reject_lookalike(self):
        x=dict(self.record,url='https://doi.org.evil.example/a')
        with self.assertRaises(ValueError):validate_record(x)
    def test_reject_credentials(self):
        x=dict(self.record,url='https://user@doi.org/a')
        with self.assertRaises(ValueError):validate_record(x)
    def test_reject_unexpected(self):
        x=dict(self.record,command='run')
        with self.assertRaises(ValueError):validate_record(x)
    def test_reject_bad_digest(self):
        x=dict(self.record,source_sha256='X'*64)
        with self.assertRaises(ValueError):validate_record(x)
    def test_dedup(self):
        a=import_records(self.db,[self.record]);b=import_records(self.db,[self.record]);self.assertEqual((a['inserted'],b['duplicates']),(1,1))
    def test_pending_only(self):
        import_records(self.db,[self.record]);self.assertEqual(self.db.execute('SELECT status FROM findings').fetchone()[0],'pending_review')
    def test_atomic_validation(self):
        bad=dict(self.record,url='https://evil.example/hi')
        with self.assertRaises(ValueError):import_records(self.db,[self.record,bad])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM findings').fetchone()[0],0)
    def test_empty_batch(self):
        with self.assertRaises(ValueError):import_records(self.db,[])
    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data.json';p.write_text(json.dumps([self.record]));q=Path(d)/'link.json';q.symlink_to(p)
            with self.assertRaises(ValueError):import_file(self.db,q)
    def test_read_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data.json';p.write_text(json.dumps([self.record]))
            self.assertEqual(import_file(self.db,p)['inserted'],1)

if __name__=='__main__':unittest.main()