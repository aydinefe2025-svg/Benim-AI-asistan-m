import hashlib
import tempfile
import unittest
from pathlib import Path
from content_verify import verify_batch

class ContentVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / 'sample.txt'
        self.file.write_bytes(b'actual research bytes')
        self.record = {'title':'Sample', 'url':'https://doi.org/10.1234/sample', 'summary':'Test', 'published':'2026-11-01', 'source_sha256':hashlib.sha256(self.file.read_bytes()).hexdigest()}
    def item(self, name='sample.txt', record=None):
        return {'file':name, 'record':record or self.record}
    def test_valid_bytes(self):
        self.assertEqual(verify_batch([self.item()], self.root)['verified'],1)
    def test_modified_bytes(self):
        self.file.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'mismatch'): verify_batch([self.item()], self.root)
    def test_forged_digest(self):
        r = dict(self.record, source_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'mismatch'): verify_batch([self.item(record=r)], self.root)
    def test_traversal(self):
        with self.assertRaises(ValueError): verify_batch([self.item('../escape')], self.root)
    def test_absolute(self):
        with self.assertRaises(ValueError): verify_batch([self.item(str(self.file))], self.root)
    def test_duplicate(self):
        with self.assertRaisesRegex(ValueError,'duplicate'): verify_batch([self.item(),self.item()], self.root)
    def test_symlink(self):
        (self.root/'link.txt').symlink_to(self.file)
        with self.assertRaisesRegex(ValueError,'symlink'): verify_batch([self.item('link.txt')], self.root)
    def test_oversize(self):
        with self.assertRaisesRegex(ValueError,'size limit'):
            from content_verify import digest_file
            digest_file(self.file,max_bytes=1)
    def test_missing(self):
        with self.assertRaises((ValueError,FileNotFoundError)): verify_batch([self.item('missing.txt')], self.root)
    def test_empty(self):
        with self.assertRaises(ValueError): verify_batch([], self.root)
    def test_unexpected_field(self):
        with self.assertRaises(ValueError): verify_batch([dict(self.item(),extra=True)],self.root)
    def test_invalid_source(self):
        r=dict(self.record,url='http://doi.org/10.1234/sample')
        with self.assertRaises(ValueError): verify_batch([self.item(record=r)],self.root)