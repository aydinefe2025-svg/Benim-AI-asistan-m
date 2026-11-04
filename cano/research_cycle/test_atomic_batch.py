import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from atomic_batch import run,audit

ITEM={'kind':'observation','title':'test','source':'local','evidence':'observed'}
class AtomicTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name);self.src=self.root/'input.jsonl';self.db=self.root/'db.sqlite3'
 def write(self,lines):self.src.write_text('\n'.join(lines)+'\n')
 def test_commit(self):
  self.write([json.dumps(ITEM)]);self.assertEqual(run(self.src,self.db)['inserted'],1);self.assertTrue(audit(self.db)['ok'])
 def test_repeat(self):
  self.write([json.dumps(ITEM)]);run(self.src,self.db);self.assertEqual(run(self.src,self.db)['already_processed'],1)
 def test_rollback(self):
  self.write([json.dumps(ITEM)])
  with self.assertRaises(RuntimeError):run(self.src,self.db,fault_after_finding=True)
  c=sqlite3.connect(self.db);self.assertEqual(c.execute('select count(*) from findings').fetchone()[0],0);self.assertEqual(c.execute('select count(*) from receipts').fetchone()[0],0);c.close()
  self.assertEqual(run(self.src,self.db)['inserted'],1)
 def test_invalid(self):
  self.write(['{invalid']);self.assertEqual(run(self.src,self.db)['rejected'],1);self.assertTrue(audit(self.db)['ok'])
 def test_duplicate_canonical(self):
  self.write([json.dumps(ITEM),json.dumps(ITEM,indent=2).replace('\n',' ')])
  r=run(self.src,self.db);self.assertEqual(r['inserted'],1);self.assertEqual(r['duplicate'],1)
 def test_orphan(self):
  self.write([json.dumps(ITEM)]);run(self.src,self.db)
  c=sqlite3.connect(self.db);c.execute('delete from findings');c.commit();c.close();self.assertFalse(audit(self.db)['ok'])
 def test_missing(self):self.assertFalse(audit(self.db)['ok'])
 def test_limit(self):
  self.write([json.dumps({**ITEM,'title':str(i)}) for i in range(3)]);r=run(self.src,self.db,1);self.assertEqual(r['deferred'],2)
 def test_symlink(self):
  self.write([json.dumps(ITEM)]);link=self.root/'link';link.symlink_to(self.src)
  with self.assertRaises(ValueError):run(link,self.db)
 def test_bad_limit(self):
  self.write([json.dumps(ITEM)])
  with self.assertRaises(ValueError):run(self.src,self.db,0)
if __name__=='__main__':unittest.main()