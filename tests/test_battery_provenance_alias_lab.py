"""Bounded deterministic synthetic provenance spelling stress, not field evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'/'battery_curve_audit'))
import provenance_alias_lab as lab

class AliasLabTests(unittest.TestCase):
    def test_1200_cases_block_synthetic_aliases_but_not_distinct_controls(self):
        x=lab.run_all(50,20261119)
        self.assertEqual(x['scenario_count'],1200)
        self.assertEqual((x['synthetic_alias_cases'],x['conservative_alias_reviews'],x['alias_escaping_split_review']),(900,900,0))
        self.assertEqual((x['synthetic_distinct_controls'],x['controls_not_blocked'],x['distinct_controls_reviewed']),(300,300,0))
        self.assertFalse(x['real_instrument_identity_verified'])

    def test_repeatability_and_counts_without_private_identifiers(self):
        a=lab.run_all(2,20261119)
        b=lab.run_all(2,20261119)
        self.assertEqual(a,b)
        self.assertEqual(a['scenario_count'],48)
        self.assertNotIn('SERIAL-',json.dumps(a))
        self.assertNotIn('SYNTHETIC-NOT-SIGNED',json.dumps(a))

    def test_bad_budgets_rejected(self):
        for n in [0,1001,-1,True,1.5]:
            with self.assertRaises(ValueError): lab.run_all(n)

    def test_cli_never_overwrites_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'report.json'
            self.assertEqual(lab.main(['--trials','1','--output',str(f)]),0)
            prior=f.read_bytes()
            with self.assertRaises(FileExistsError): lab.main(['--trials','1','--output',str(f)])
            self.assertEqual(f.read_bytes(),prior)

if __name__=='__main__':unittest.main()
