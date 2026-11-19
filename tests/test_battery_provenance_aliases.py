"""Regression: conservative provenance matching under harmless metadata spelling changes.

These are synthetic metadata only. Blocking a split is a safety review, never
proof that two real physical cells, devices or experiments coincide.
"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'battery_curve_audit'))
import field_pilot_evidence as pilot


def ledger():
    cells = 'ABCD'
    return {
        'schema': pilot.SCHEMA,
        'site_authorization': {'permitted': True, 'reference': 'SYNTHETIC-ONLY'},
        'audit_receipt_sha256': 'a'*64,
        'cells': [{'cell':c, 'device':'INSTR-'+c, 'batch':'BATCH-'+c,
                   'campaign':'CAMPAIGN-'+c} for c in cells],
        'assignments': [{'cell':c,'partition':p} for c,p in
                        zip(cells,('train','validation','test','train'))],
        'screened_pair_count': 6, 'screened_flagged_count': 0,
        'reviews': [{'a':'A','b':'B','flagged':False,
                     'reviewer_a':{'id':'T1','verdict':'independent'},
                     'reviewer_b':{'id':'T2','verdict':'independent'}}],
    }

class ProvenanceAliasTests(unittest.TestCase):
    def test_device_case_and_whitespace_alias_cannot_escape_split_guard(self):
        x=ledger()
        x['cells'][1]['device']='   instr-a   '
        result=pilot.assess(x)
        self.assertEqual(result['decision'],'BLOCK_PROVENANCE_LEAKAGE')
        self.assertGreater(result['cross_split_metadata_links'], 0)

    def test_batch_unicode_nfkc_alias_cannot_escape_split_guard(self):
        x=ledger()
        x['cells'][1]['batch']='ＢＡＴＣＨ-Ａ'
        result=pilot.assess(x)
        self.assertEqual(result['decision'],'BLOCK_PROVENANCE_LEAKAGE')
        self.assertGreater(result['cross_split_metadata_links'], 0)

    def test_campaign_case_alias_cannot_escape_split_guard(self):
        x=ledger()
        x['cells'][2]['campaign']='campaign-a'
        result=pilot.assess(x)
        self.assertEqual(result['decision'],'BLOCK_PROVENANCE_LEAKAGE')
        self.assertGreater(result['cross_split_metadata_links'], 0)

    def test_control_code_in_provenance_identifier_is_rejected(self):
        x=ledger()
        x['cells'][1]['device']='INSTR-A\u200b'  # invisible format control
        with self.assertRaisesRegex(ValueError, 'format|control|metadata'):
            pilot.assess(x)

    def test_normalized_shared_device_within_same_partition_is_not_cross_split(self):
        x=ledger()
        x['cells'][3]['device']='  instr-a '
        result=pilot.assess(x)
        self.assertEqual(result['decision'],'PILOT_METRICS_ONLY')
        self.assertEqual(result['provenance_connected_groups'],3)
        self.assertEqual(result['cross_split_metadata_links'],0)

    def test_original_different_metadata_remains_pilot_not_certified(self):
        result=pilot.assess(ledger())
        self.assertEqual(result['decision'],'PILOT_METRICS_ONLY')
        self.assertEqual(result['field_acceptance'],'NOT_ESTABLISHED')
        self.assertEqual(result['cross_split_metadata_links'],0)

    def test_safeguard_does_not_leak_private_identifiers(self):
        x=ledger()
        x['cells'][1]['device']='   instr-a   '
        text=json.dumps(pilot.assess(x),ensure_ascii=False)
        for private in ['INSTR-A','instr-a','BATCH-A','CAMPAIGN-A',
                        'SYNTHETIC-ONLY','T1','T2']:
            self.assertNotIn(private,text)

if __name__=='__main__':unittest.main()
