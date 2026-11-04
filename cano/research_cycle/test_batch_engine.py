from contextlib import closing
import json
import tempfile
import unittest
from pathlib import Path
import batch_engine
import feedback_loop

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.source=root/'input.jsonl';self.ledger=root/'ledger.db';self.findings=root/'findings.db'
        self.items=[{'kind':'observation','title':f'Observation {i}','source':'local-test','evidence':f'evidence {i}'} for i in range(4)]
    def write(self,items):self.source.write_text('\n'.join(json.dumps(x) if not isinstance(x,str) else x for x in items))
    def run_batch(self,limit=1000):return batch_engine.run(self.source,self.ledger,self.findings,limit)
    def test_bulk_ingest(self):
        self.write(self.items);self.assertEqual(self.run_batch()['inserted'],4)
        with closing(feedback_loop.connect(self.findings)) as c:self.assertEqual(feedback_loop.report(c)['counts']['pending_review'],4)
    def test_idempotent(self):
        self.write(self.items);self.run_batch();self.assertEqual(self.run_batch()['already_processed'],4)
    def test_bounded_and_resume(self):
        self.write(self.items);a=self.run_batch(2);self.assertEqual((a['inserted'],a['deferred']),(2,2))
        b=self.run_batch(2);self.assertEqual((b['inserted'],b['deferred']),(2,0))
    def test_rejected_is_recorded(self):
        self.write([self.items[0],'not-json',self.items[1]]);self.assertEqual(self.run_batch()['rejected'],1)
    def test_duplicate_semantics(self):
        self.write([self.items[0],dict(self.items[0])]);a=self.run_batch();self.assertEqual(a['already_processed'],1)
    def test_existing_finding(self):
        with closing(feedback_loop.connect(self.findings)) as c:feedback_loop.ingest(c,self.items[0])
        self.write([self.items[0]]);self.assertEqual(self.run_batch()['duplicate'],1)
    def test_oversized(self):
        self.source.write_bytes(b'a'*(batch_engine.MAX_FILE+1))
        with self.assertRaises(ValueError):self.run_batch()
    def test_invalid_limit(self):
        self.write(self.items)
        with self.assertRaises(ValueError):self.run_batch(0)
    def test_symlink(self):
        self.write(self.items);other=self.source.parent/'link';other.symlink_to(self.source)
        with self.assertRaises(ValueError):batch_engine.run(other,self.ledger,self.findings)
    def test_no_automatic_acceptance(self):
        self.write(self.items);self.run_batch()
        with closing(feedback_loop.connect(self.findings)) as c:self.assertEqual(feedback_loop.report(c)['reviewed'],0)
if __name__=='__main__':unittest.main()