import json
from pathlib import Path
import tempfile
import unittest
from run_hierarchy_experiment import main

class CLI(unittest.TestCase):
    def test_writes_and_replays_deterministic_json(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'out.json'
            self.assertEqual(main(['--output',str(a)]),0)
            first=a.read_bytes()
            self.assertEqual(main(['--output',str(a)]),0)
            self.assertEqual(first,a.read_bytes())
            p=json.loads(first)
            self.assertFalse(p['paper_win_rates_replicated'])
            self.assertEqual(p['group_sensitivity']['cases'],128)
    def test_missing_parent_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):main(['--output',str(Path(d)/'not_created'/'result.json')])
    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'data.json';target.write_text('{}')
            link=Path(d)/'link.json';link.symlink_to(target)
            with self.assertRaises(ValueError):main(['--output',str(link)])
            self.assertEqual(target.read_text(),'{}')
if __name__=='__main__':unittest.main()
