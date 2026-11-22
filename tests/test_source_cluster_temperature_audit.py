import copy
from fractions import Fraction
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'/'battery_curve_audit'))
from source_cluster_temperature_audit import evaluate, validate, canonical_source_bytes, EXPECTED_SHA256

SOURCE=ROOT/'research'/'battery_curve_audit'/'fixtures'/'k01_k04_k05_nine_source_27_pairs_pinned.json'

class SourceClusteredAuditTests(unittest.TestCase):
    def setUp(self): self.data=json.loads(SOURCE.read_text(encoding='utf-8'))
    def test_canonical_pinned_lf_bytes(self):
        raw=SOURCE.read_bytes().replace(b'\r\n',b'\n')
        self.assertEqual(canonical_source_bytes(raw),raw)
    def test_windows_crlf_checkout_normalized(self):
        raw=SOURCE.read_bytes().replace(b'\r\n',b'\n')
        self.assertEqual(canonical_source_bytes(raw.replace(b'\n',b'\r\n')),raw)
    def test_corrupted_crlf_checkout_rejected(self):
        raw=SOURCE.read_bytes().replace(b'\r\n',b'\n')
        with self.assertRaises(ValueError):
            canonical_source_bytes(raw.replace(b'\n',b'\r\n')+b'changed')
    def test_real_source_summary_clusters(self):
        by_id,events=validate(self.data)
        self.assertEqual((len(by_id),len(events)),(9,4))
        self.assertEqual([47627092,47627104,47627110,47639005],sorted(events))
    def test_exact_enumeration(self):
        r=evaluate(self.data,'pinned')
        self.assertEqual(r['exact_label_assignment_count'],81)
        self.assertEqual(r['conditional_uniform_null']['any_temperature_probability_exact'],'1/27')
        self.assertEqual(r['conditional_uniform_null']['prespecified_10C_probability_exact'],'1/81')
        self.assertEqual(r['discordant_by_temperature'],{'10':4,'23':0,'45':0})
    def test_skew_sensitivity(self):
        r=evaluate(self.data,'pinned')
        vals=[v['any_temperature_probability'] for v in r['unequal_temperature_label_sensitivity']]
        for x,y in zip(vals,[1/27,.0418,.0703125,.1328]): self.assertAlmostEqual(x,y)
    def test_leave_one_discordant_source_out(self):
        r=evaluate(self.data,'pinned')
        vals=[v['any_temperature_probability'] for v in r['leave_one_source_out'] if v['removed_source_discordant']]
        self.assertEqual(vals,[1/9]*4)
    def test_source_duplicate_rejected(self):
        d=copy.deepcopy(self.data); d['source_results'][1]['temperature_C']=10
        with self.assertRaises(ValueError):validate(d)
    def test_nonfinite_rejected(self):
        d=copy.deepcopy(self.data);d['source_results'][0]['charge_change_percent']=float('nan')
        with self.assertRaises(ValueError):validate(d)
    def test_bad_source_count_rejected(self):
        d=copy.deepcopy(self.data); d['source_file_records']=27
        with self.assertRaises(ValueError):validate(d)
    def test_fake_causal_claim_rejected(self):
        d=copy.deepcopy(self.data);d['temperature_causality_established']=True
        with self.assertRaises(ValueError):validate(d)
    def test_fake_production_claim_rejected(self):
        d=copy.deepcopy(self.data);d['production_release_allowed']=True
        with self.assertRaises(ValueError):validate(d)
    def test_sign_flag_mismatch_rejected(self):
        d=copy.deepcopy(self.data);d['source_results'][0]['mixed_or_zero_channel_sign']=True
        with self.assertRaises(ValueError):validate(d)
    def test_missing_temperature_rejected(self):
        d=copy.deepcopy(self.data);d['source_results'].pop()
        with self.assertRaises(ValueError):validate(d)
    def test_false_independent_replicate_rejected(self):
        d=copy.deepcopy(self.data); d['source_results'][0]['source_file_id']=123456789
        with self.assertRaises(ValueError):validate(d)

if __name__=='__main__': unittest.main()