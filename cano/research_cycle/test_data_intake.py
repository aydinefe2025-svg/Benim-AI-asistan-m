import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from data_intake import inspect, inspect_zip

class IntakeTests(unittest.TestCase):
    def test_directory_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'a.txt').write_text('abc')
            result=inspect(p)
            self.assertTrue(result['passed']);self.assertEqual(result['count'],1)
            self.assertEqual(result['files'][0]['sha256'],'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    def test_zip_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.zip'
            with ZipFile(p,'w') as z:z.writestr('safe/a.txt','abc')
            self.assertEqual(inspect_zip(p)['count'],1)
    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.zip'
            with ZipFile(p,'w') as z:z.writestr('../escape','abc')
            with self.assertRaisesRegex(ValueError,'unsafe'):inspect_zip(p)
    def test_duplicate_rejected(self):
        import warnings
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'dup.zip'
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with ZipFile(p,'w') as z:
                    z.writestr('a','abc');z.writestr('a','xyz')
            with self.assertRaisesRegex(ValueError,'duplicate'):inspect_zip(p)
    def test_budget(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'a').write_text('abcdef')
            with self.assertRaisesRegex(ValueError,'budget'):inspect(p,max_bytes=3)
    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'a').write_text('x')
            try:(p/'b').symlink_to(p/'a')
            except OSError:self.skipTest('symlinks unavailable')
            with self.assertRaisesRegex(ValueError,'symlink'):inspect(p)
if __name__=='__main__':unittest.main()