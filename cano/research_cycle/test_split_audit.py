import csv
import tempfile
import unittest
from pathlib import Path
from split_audit import audit, load_csv, FIELDS

def row(i,scene,split,a=None,b=None):
    return {'pair_id':str(i),'scene_id':scene,'split':split,'image_a_sha256':a or f'{i:064x}','image_b_sha256':b or f'{i+100:064x}'}

class SplitAuditTests(unittest.TestCase):
    def test_clean_scene_split(self): self.assertTrue(audit([row(1,'s1','train'),row(2,'s2','test')])['ok'])
    def test_scene_leak(self): self.assertIn('scene_leakage',[x['kind'] for x in audit([row(1,'s','train'),row(2,'s','test')])['issues']])
    def test_image_leak(self): self.assertIn('image_leakage',[x['kind'] for x in audit([row(1,'s1','train'),row(2,'s2','test',a=f'{1:064x}')])['issues']])
    def test_duplicate_pair(self): self.assertIn('duplicate_pair_id',[x['kind'] for x in audit([row(1,'s1','train'),row(1,'s2','test')])['issues']])
    def test_one_split_fails(self): self.assertFalse(audit([row(1,'s1','train')])['ok'])
    def test_empty_rejected(self):
        with self.assertRaises(ValueError): audit([])
    def test_unknown_split_rejected(self):
        with self.assertRaises(ValueError): audit([row(1,'s','eval')])
    def test_bad_digest_rejected(self):
        with self.assertRaises(ValueError): audit([row(1,'s','train',a='abc')])
    def test_extra_field_rejected(self):
        with self.assertRaises(ValueError): audit([{**row(1,'s','train'),'other':'x'}])
    def test_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data.csv'
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=sorted(FIELDS)); w.writeheader(); w.writerows([row(1,'s1','train'),row(2,'s2','val')])
            self.assertTrue(load_csv(p)['ok'])
    def test_csv_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'link.csv'; p.symlink_to(Path(d)/'real.csv')
            with self.assertRaises(ValueError): load_csv(p)
    def test_csv_duplicate_header_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data.csv'; p.write_text('pair_id,pair_id,scene_id,split,image_a_sha256,image_b_sha256\n')
            with self.assertRaises(ValueError): load_csv(p)