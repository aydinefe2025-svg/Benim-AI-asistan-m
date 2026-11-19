"""Fail-closed CSV-to-raw-source battery field provenance bridge; synthetic only."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'research'/'battery_curve_audit'))
import integrated_customer_gate as gate
import field_source_csv_bridge as bridge


def curve(level):
    return 'Timestamp_1 [h],DC1 [V]\n' + '\n'.join(
        f'{i},{level-i*0.003:.5f}' for i in range(120)) + '\n'


class BoundCSVTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        files=[]
        for cell, level in zip('ABCD',(4.2,3.9,3.6,3.3)):
            (self.root/(cell+'.csv')).write_text(curve(level),encoding='utf-8')
            files.append({'path':cell+'.csv','cell':cell,'mode':'dchg'})
        self.manifest={'schema':'cano.battery.customer-files.v1','files':files}
        self.mp=self.root/'manifest.json'
        self.mp.write_text(json.dumps(self.manifest),encoding='utf-8')
        self.refresh_source()
        self.cells=self.root/'cells.csv'
        self.reviews=self.root/'reviews.csv'
        self.frame=self.root/'frame.json'
        self.out=self.root/'summary.json'
        self.private=self.root/'private.json'
        self.write_cells()
        self.reviews.write_text('a,b,flagged,reviewer_a_id,reviewer_a_verdict,reviewer_b_id,reviewer_b_verdict\nA,B,false,TECH_A,independent,TECH_B,independent\n',encoding='utf-8')
        self.write_frame()

    def refresh_source(self):
        self.report=gate.integrated_check(self.manifest,self.root)
        self.audit=self.root/'private-source-audit.json'
        self.audit.write_text(json.dumps(self.report,ensure_ascii=False,sort_keys=True),encoding='utf-8')
        self.part={x['cell']:x['partition'] for x in self.report['split']['assignments']} if self.report['split'] else {}

    def write_cells(self, mutation=None):
        rows=['cell,device,batch,campaign,partition']
        for cell in 'ABCD':
            device='DEV-'+cell
            partition=self.part.get(cell,'train')
            if mutation and cell==mutation.get('cell'):
                device=mutation.get('device',device)
                partition=mutation.get('partition',partition)
            rows.append(f'{cell},{device},BATCH-{cell},CAMPAIGN-{cell},{partition}')
        self.cells.write_text('\n'.join(rows)+'\n',encoding='utf-8')

    def write_frame(self, receipt=None):
        doc={'schema':'cano.battery.field-intake-frame.v1',
             'site_authorization':{'permitted':True,'reference':'PRIVATE-SYNTHETIC-ONLY'},
             'audit_receipt_sha256':receipt or hashlib.sha256(self.audit.read_bytes()).hexdigest(),
             'screened_pair_count':6,'screened_flagged_count':0}
        self.frame.write_text(json.dumps(doc),encoding='utf-8')

    def args(self, out=None, private=None):
        a=['--manifest',str(self.mp),'--root',str(self.root),
           '--audit-report',str(self.audit),'--cells',str(self.cells),
           '--reviews',str(self.reviews),'--frame',str(self.frame),
           '--summary',str(out or self.out)]
        if private is not None:a+=['--private-ledger',str(private)]
        return a

    def test_valid_bound_sources_and_reviewers_only_pilot_not_certificate(self):
        self.assertEqual(bridge.main(self.args()),0)
        result=json.loads(self.out.read_text())
        self.assertEqual(result['decision'],'PILOT_ONLY_NOT_CERTIFIED')
        self.assertEqual(result['field_acceptance'],'NOT_ESTABLISHED')
        self.assertTrue(result['source_recalculated_and_matched'])
        self.assertTrue(result['receipt_and_partitions_bound'])
        self.assertEqual(result['field_counts']['consensus']['tn'],1)
        for private in ('PRIVATE-SYNTHETIC-ONLY','TECH_A','DEV-A','A.csv','audit_receipt_sha256'):
            self.assertNotIn(private,self.out.read_text())
        if os.name=='posix':self.assertEqual(self.out.stat().st_mode&0o777,0o600)

    def test_bogus_receipt_blocks_before_creating_any_report(self):
        self.write_frame('0'*64)
        self.assertEqual(bridge.main(self.args()),2)
        self.assertFalse(self.out.exists())

    def test_changed_raw_source_is_reaudited_and_rejected(self):
        (self.root/'A.csv').write_text(curve(4.15))
        self.assertEqual(bridge.main(self.args()),2)
        self.assertFalse(self.out.exists())

    def test_tampered_source_audit_even_when_receipt_updated(self):
        doc=json.loads(self.audit.read_text())
        doc['decision']='REVIEW_REQUIRED'
        self.audit.write_text(json.dumps(doc),encoding='utf-8')
        self.write_frame()
        self.assertEqual(bridge.main(self.args()),2)
        self.assertFalse(self.out.exists())

    def test_partition_forgery_is_refused(self):
        bad='test' if self.part['A']!='test' else 'train'
        self.write_cells({'cell':'A','partition':bad})
        self.assertEqual(bridge.main(self.args()),2)
        self.assertFalse(self.out.exists())

    def test_shared_device_cross_partition_blocks_and_still_redacts(self):
        other=next(c for c in 'BCD' if self.part[c]!=self.part['A'])
        self.write_cells({'cell':other,'device':'DEV-A'})
        self.assertEqual(bridge.main(self.args()),2)
        doc=json.loads(self.out.read_text())
        self.assertEqual(doc['decision'],'BLOCK_PROVENANCE_LEAKAGE')
        self.assertGreater(doc['field_counts']['cross_split_metadata_links'],0)
        self.assertNotIn('DEV-A',self.out.read_text())

    def test_two_reviewers_cross_partition_link_blocks(self):
        other=next(c for c in 'BCD' if self.part[c]!=self.part['A'])
        self.reviews.write_text('a,b,flagged,reviewer_a_id,reviewer_a_verdict,reviewer_b_id,reviewer_b_verdict\nA,'+other+',false,TECH_A,linked,TECH_B,linked\n',encoding='utf-8')
        self.assertEqual(bridge.main(self.args()),2)
        self.assertEqual(json.loads(self.out.read_text())['decision'],'BLOCK_PROVENANCE_LEAKAGE')

    def test_source_duplicate_never_receives_field_green(self):
        (self.root/'B.csv').write_text((self.root/'A.csv').read_text())
        self.refresh_source();self.write_cells();self.write_frame()
        self.assertEqual(self.report['decision'],'REVIEW_REQUIRED')
        self.assertEqual(bridge.main(self.args()),2)
        self.assertEqual(json.loads(self.out.read_text())['decision'],'BLOCK_AUDIT_REVIEW')

    def test_existing_output_is_not_replaced(self):
        self.out.write_bytes(b'ORIGINAL-OWNER-FILE')
        self.assertEqual(bridge.main(self.args()),2)
        self.assertEqual(self.out.read_bytes(),b'ORIGINAL-OWNER-FILE')

    def test_output_cannot_clobber_any_input(self):
        for victim in (self.mp,self.audit,self.cells,self.reviews,self.frame,self.root/'A.csv'):
            before=victim.read_bytes()
            self.assertEqual(bridge.main(self.args(out=victim)),2)
            self.assertEqual(victim.read_bytes(),before)

    def test_sensitive_ledger_only_when_explicitly_requested(self):
        self.assertEqual(bridge.main(self.args(private=self.private)),0)
        ledger=json.loads(self.private.read_text())
        self.assertEqual(ledger['site_authorization']['reference'],'PRIVATE-SYNTHETIC-ONLY')
        self.assertEqual(len(ledger['cells']),4)
        self.assertNotIn('PRIVATE-SYNTHETIC-ONLY',self.out.read_text())
        if os.name=='posix':self.assertEqual(self.private.stat().st_mode&0o777,0o600)

    def test_private_output_collision_is_atomic(self):
        self.assertEqual(bridge.main(self.args(private=self.mp)),2)
        self.assertFalse(self.out.exists())
        self.assertEqual(json.loads(self.mp.read_text())['schema'],'cano.battery.customer-files.v1')

    def test_invalid_csv_pair_is_refused_without_output(self):
        self.reviews.write_text('a,b,flagged,reviewer_a_id,reviewer_a_verdict,reviewer_b_id,reviewer_b_verdict\nA,A,false,TECH_A,independent,TECH_B,independent\n',encoding='utf-8')
        self.assertEqual(bridge.main(self.args()),2)
        self.assertFalse(self.out.exists())

    def test_unverified_authorization_is_blocked(self):
        data=json.loads(self.frame.read_text());data['site_authorization']['permitted']=False
        self.frame.write_text(json.dumps(data),encoding='utf-8')
        self.assertEqual(bridge.main(self.args()),2)
        self.assertFalse(self.out.exists())

    def test_partial_unlabeled_review_is_not_assumed_ground_truth(self):
        self.reviews.write_text('a,b,flagged,reviewer_a_id,reviewer_a_verdict,reviewer_b_id,reviewer_b_verdict\nA,B,false,TECH_A,unknown,TECH_B,independent\n',encoding='utf-8')
        self.assertEqual(bridge.main(self.args()),0)
        result=json.loads(self.out.read_text())
        self.assertEqual(result['field_counts']['unresolved'],1)
        self.assertEqual(result['field_counts']['consensus_reviewed'],0)
        self.assertIsNone(result['field_counts']['rates']['false_negative_rate'])

if __name__=='__main__':unittest.main()
