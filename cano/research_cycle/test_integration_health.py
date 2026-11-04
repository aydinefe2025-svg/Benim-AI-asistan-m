import unittest, tempfile, pathlib
from integration_health import validate,summary,append
R={'service':'notion','status':'verified','checked_at':'2026-11-01T20:00:00+00:00','detail':'Read-only fetch succeeded'}
class IntegrationTests(unittest.TestCase):
 def test_empty_not_ready(self): self.assertFalse(summary([])['ready'])
 def test_single_not_ready(self): self.assertFalse(summary([R])['ready'])
 def test_both_ready(self): self.assertTrue(summary([R,{**R,'service':'github'}])['ready'])
 def test_blocked_not_ready(self): self.assertFalse(summary([R,{**R,'service':'github','status':'blocked'}])['ready'])
 def test_later_overrides(self): self.assertFalse(summary([R,{**R,'status':'blocked','checked_at':'2026-11-01T21:00:00+00:00'}])['ready'])
 def test_unknown_rejected(self):
  with self.assertRaises(ValueError): validate({**R,'service':'evil'})
 def test_naive_time_rejected(self):
  with self.assertRaises(ValueError): validate({**R,'checked_at':'2026-11-01T20:00:00'})
 def test_schema_rejected(self):
  with self.assertRaises(ValueError): validate({**R,'secret':'x'})
 def test_append_roundtrip(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'ledger.json'; append(p,R); self.assertEqual(summary(__import__('json').loads(p.read_text()))['services']['notion']['status'],'verified')
 def test_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'ledger.json'; p.symlink_to(pathlib.Path(d)/'other.json')
   with self.assertRaises(ValueError): append(p,R)