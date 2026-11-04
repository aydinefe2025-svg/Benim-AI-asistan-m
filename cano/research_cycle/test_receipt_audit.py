import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
import batch_engine
import receipt_audit

class ReceiptAuditTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        p=Path(self.t.name);self.src=p/'data.jsonl';self.ledger=p/'ledger.db';self.findings=p/'findings.db'
        self.src.write_text(json.dumps({'kind':'observation','title':'test','source':'local','evidence':'fixture'}))
    def ingest(self):batch_engine.run(self.src,self.ledger,self.findings)
    def test_good(self):
        self.ingest();self.assertTrue(receipt_audit.audit(self.ledger,self.findings)['ok'])
    def test_missing_databases(self):
        self.assertFalse(receipt_audit.audit(self.ledger,self.findings)['ok'])
    def test_missing_finding_detected(self):
        self.ingest()
        with closing(sqlite3.connect(self.findings)) as c:
            c.execute('DELETE FROM findings'); c.commit()
        self.assertFalse(receipt_audit.audit(self.ledger,self.findings)['ok'])
    def test_invalid_status_detected(self):
        self.ingest()
        with closing(sqlite3.connect(self.ledger)) as c:
            c.execute("UPDATE receipts SET status='pretend-success'"); c.commit()
        self.assertFalse(receipt_audit.audit(self.ledger,self.findings)['ok'])
    def test_rejected_receipt_allowed(self):
        self.src.write_text('not json');self.ingest()
        self.assertTrue(receipt_audit.audit(self.ledger,self.findings)['ok'])
    def test_empty_receipts_not_success(self):
        self.ingest()
        with closing(sqlite3.connect(self.ledger)) as c:
            c.execute('DELETE FROM receipts'); c.commit()
        self.assertFalse(receipt_audit.audit(self.ledger,self.findings)['ok'])
if __name__=='__main__':unittest.main()