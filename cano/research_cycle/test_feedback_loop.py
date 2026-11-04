import sqlite3
import tempfile
import unittest
from pathlib import Path
import feedback_loop as f

ITEM={'kind':'observation','title':'Test','source':'local:test','evidence':'synthetic fixture'}
class TestFeedback(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=f.connect(Path(self.tmp.name)/'test.sqlite3')
    def tearDown(self):
        self.c.close();self.tmp.cleanup()
    def test_dedup(self):
        self.assertTrue(f.ingest(self.c,ITEM)['inserted'])
        self.assertFalse(f.ingest(self.c,ITEM)['inserted'])
        self.assertEqual(f.report(self.c)['counts']['pending_review'],1)
    def test_review(self):
        d=f.ingest(self.c,ITEM)['digest']
        self.assertEqual(f.review(self.c,d,'accepted','verified by reviewer')['status'],'accepted')
        self.assertEqual(f.report(self.c)['reviewed'],1)
        with self.assertRaises(ValueError):f.review(self.c,d,'accepted','again')
    def test_reject_untrusted_kind(self):
        with self.assertRaises(ValueError):f.ingest(self.c,{**ITEM,'kind':'execute'})
    def test_reject_missing_evidence(self):
        with self.assertRaises(ValueError):f.ingest(self.c,{**ITEM,'evidence':''})
    def test_no_automatic_acceptance(self):
        f.ingest(self.c,ITEM)
        self.assertEqual(f.report(self.c)['reviewed'],0)
    def test_invalid_review(self):
        with self.assertRaises(ValueError):f.review(self.c,'missing','accepted','reason')
    def test_persistence(self):
        f.ingest(self.c,ITEM)
        self.c.close()
        self.c=f.connect(Path(self.tmp.name)/'test.sqlite3')
        self.assertEqual(f.report(self.c)['counts']['pending_review'],1)
    def test_source_required(self):
        with self.assertRaises(ValueError):f.ingest(self.c,{**ITEM,'source':' '})
if __name__=='__main__':unittest.main()