import unittest, tempfile, pathlib, zipfile, io, hashlib, contextlib
import f87_fetch_source_probe as src

class SourceFingerprintFailClosed(unittest.TestCase):
 def test_publisher_md5_pinned(self):
  self.assertEqual(src.EXPECTED_MD5,'ccc2fbef2b0f51df389ff8f7d9b00608')
 def test_corrupt_file_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(RuntimeError):src.probe(b'garbage',t)
 def test_fake_missing_source_rejected(self):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('eos.nb','2\n0.1\n0.2')
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaisesRegex(RuntimeError,'MISSING_COMPOSE_PHYSICS_SOURCE'):src.probe(out.getvalue(),t,hashlib.md5(out.getvalue()).hexdigest())
 def test_fake_but_complete_parses_both(self):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:
   z.writestr('nested/eos.nb','2\n0.1\n0.2\n')
   z.writestr('nested/eos.thermo','939.565 938.272 1\n1 1 1 100 0 0 0 0 0 0 0\n')
  with tempfile.TemporaryDirectory() as t:
   data=src.probe(out.getvalue(),t,hashlib.md5(out.getvalue()).hexdigest())
   self.assertEqual(data['status'],'SYNTHETIC_TEST_ONLY')
   self.assertEqual(data['baryon_density_grid_first_tokens'],['2','0.1','0.2'])
   self.assertEqual((pathlib.Path(t)/'eos.thermo').stat().st_size,len('939.565 938.272 1\n1 1 1 100 0 0 0 0 0 0 0\n'))

if __name__=='__main__':unittest.main()
