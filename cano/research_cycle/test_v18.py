import json,sqlite3,tempfile,unittest
from contextlib import closing
from pathlib import Path
import atomic_batch

class AtomicAuditTampering(unittest.TestCase):
 def test_content_mutation_detected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); inp=root/'in.jsonl'; db=root/'db.sqlite3'
   inp.write_text(json.dumps({'kind':'observation','title':'x','source':'lab','evidence':'y'})+'\n')
   self.assertEqual(atomic_batch.run(inp,db)['inserted'],1)
   self.assertTrue(atomic_batch.audit(db)['ok'])
   with closing(sqlite3.connect(db)) as c:
    c.execute("UPDATE findings SET evidence='tampered'"); c.commit()
   self.assertFalse(atomic_batch.audit(db)['ok'])
 def test_unchanged_data_passes(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);inp=root/'in.jsonl';db=root/'db.sqlite3'
   inp.write_text(json.dumps({'kind':'issue','title':'test','source':'lab','evidence':'proof'})+'\n')
   atomic_batch.run(inp,db)
   self.assertEqual(atomic_batch.audit(db)['errors'],[])