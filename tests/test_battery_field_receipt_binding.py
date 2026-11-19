"""Synthetic provenance/source linkage tests; no customer data or field proof."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'/'battery_curve_audit'))
import integrated_customer_gate as gate
import field_receipt_binding as link


def measurement(level):
    return 'Timestamp_1 [h],DC1 [V]\n' + '\n'.join(
        f'{i},{level-i*0.003:.5f}' for i in range(120)) + '\n'


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.entries=[]
        for name, level in zip('ABCD',(4.2,3.9,3.6,3.3)):
            filename=name+'.csv'
            (self.root/filename).write_text(measurement(level))
            self.entries.append({'path':filename,'cell':name,'mode':'dchg'})
        self.manifest={'schema':'cano.battery.customer-files.v1','files':self.entries}
        self.report=gate.integrated_check(self.manifest,self.root)
        self.raw=json.dumps(self.report,sort_keys=True,ensure_ascii=False).encode('utf-8')
        self.ledger=self.make_ledger()

    def make_ledger(self):
        cell_partitions={c['cell']:c['partition'] for c in self.report['split']['assignments']}
        return {
            'schema':'cano.battery.field-pilot.v1',
            'site_authorization':{'permitted':True,'reference':'SYNTHETIC-ONLY'},
            'audit_receipt_sha256':hashlib.sha256(self.raw).hexdigest(),
            'cells':[{'cell':n,'device':'D-'+n,'batch':'B-'+n,'campaign':'C-'+n} for n in 'ABCD'],
            'assignments':[{'cell':n,'partition':cell_partitions[n]} for n in 'ABCD'],
            'screened_pair_count':6,'screened_flagged_count':0,
            'reviews':[{'a':'A','b':'B','flagged':False,
                        'reviewer_a':{'id':'T1','verdict':'independent'},
                        'reviewer_b':{'id':'T2','verdict':'independent'}}]
        }

    def test_properly_bound_clean_screen_remains_not_certified(self):
        got=link.bind_pilot(self.manifest,self.root,self.raw,self.ledger)
        self.assertEqual(got['decision'],'PILOT_ONLY_NOT_CERTIFIED')
        self.assertEqual(got['field_acceptance'],'NOT_ESTABLISHED')
        self.assertTrue(got['source_recalculated_and_matched'])
        self.assertTrue(got['receipt_and_partitions_bound'])
        self.assertEqual(got['field_counts']['consensus']['tn'],1)
        self.assertNotIn('A.csv',json.dumps(got))
        self.assertNotIn('SYNTHETIC-ONLY',json.dumps(got))
        self.assertNotIn('audit_receipt_sha256',json.dumps(got))

    def test_wrong_report_receipt_refused(self):
        self.ledger['audit_receipt_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'receipt'):
            link.bind_pilot(self.manifest,self.root,self.raw,self.ledger)

    def test_tampered_report_even_with_updated_receipt_refused(self):
        bogus=copy.deepcopy(self.report)
        bogus['decision']='PASS_IMPOSSIBLE'
        altered=json.dumps(bogus,sort_keys=True).encode()
        self.ledger['audit_receipt_sha256']=hashlib.sha256(altered).hexdigest()
        with self.assertRaisesRegex(ValueError,'(altered|mismatch)'):
            link.bind_pilot(self.manifest,self.root,altered,self.ledger)

    def test_changed_original_measurement_refused(self):
        (self.root/'A.csv').write_text(measurement(4.0))
        with self.assertRaisesRegex(ValueError,'(altered|mismatch)'):
            link.bind_pilot(self.manifest,self.root,self.raw,self.ledger)

    def test_ledger_forged_partition_refused(self):
        first=self.ledger['assignments'][0]
        first['partition']='test' if first['partition']!='test' else 'train'
        with self.assertRaisesRegex(ValueError,'partition'):
            link.bind_pilot(self.manifest,self.root,self.raw,self.ledger)

    def test_ledger_missing_cell_refused(self):
        self.ledger['cells'].pop()
        self.ledger['assignments'].pop()
        with self.assertRaisesRegex(ValueError,'cell'):
            link.bind_pilot(self.manifest,self.root,self.raw,self.ledger)

    def test_shared_device_cross_split_blocks(self):
        partitions={row['cell']:row['partition'] for row in self.ledger['assignments']}
        a='A';b=next(c for c in 'BCD' if partitions[c]!=partitions[a])
        other=next(item for item in self.ledger['cells'] if item['cell']==b)
        other['device']='D-A'
        got=link.bind_pilot(self.manifest,self.root,self.raw,self.ledger)
        self.assertEqual(got['decision'],'BLOCK_PROVENANCE_LEAKAGE')
        self.assertGreater(got['field_counts']['cross_split_metadata_links'],0)

    def test_source_review_not_auto_accepted_despite_valid_metadata(self):
        (self.root/'B.csv').write_text((self.root/'A.csv').read_text())
        self.report=gate.integrated_check(self.manifest,self.root)
        self.assertEqual(self.report['decision'],'REVIEW_REQUIRED')
        self.raw=json.dumps(self.report,sort_keys=True).encode()
        self.ledger=self.make_ledger()
        got=link.bind_pilot(self.manifest,self.root,self.raw,self.ledger)
        self.assertEqual(got['decision'],'BLOCK_AUDIT_REVIEW')
        self.assertEqual(got['field_acceptance'],'NOT_ESTABLISHED')

    def test_insufficient_split_not_accepted(self):
        self.manifest['files']=self.manifest['files'][:3]
        for row in self.manifest['files']:
            (self.root/row['path']).write_text(measurement(4.2))
        self.report=gate.integrated_check(self.manifest,self.root)
        self.assertIsNone(self.report['split'])
        self.raw=json.dumps(self.report,sort_keys=True).encode()
        self.ledger['audit_receipt_sha256']=hashlib.sha256(self.raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'split'):
            link.bind_pilot(self.manifest,self.root,self.raw,self.ledger)

    def test_main_writes_redacted_summary_once_and_never_overwrites_inputs(self):
        manifest=self.root/'manifest.json'
        evidence=self.root/'audit.json'
        ledger=self.root/'private-ledger.json'
        summary=self.root/'redacted.json'
        manifest.write_text(json.dumps(self.manifest))
        evidence.write_bytes(self.raw)
        ledger.write_text(json.dumps(self.ledger))
        args=['--manifest',str(manifest),'--root',str(self.root),'--audit-report',str(evidence),'--ledger',str(ledger),'--summary',str(summary)]
        self.assertEqual(link.main(args),0)
        content=summary.read_text()
        for forbidden in ('A.csv','SYNTHETIC-ONLY','D-A','T1','audit_receipt_sha256'):
            self.assertNotIn(forbidden,content)
        self.assertEqual(link.main(args),2)
        self.assertEqual(summary.read_text(),content)
        self.assertEqual(link.main(args[:-1]+[str(manifest)]),2)
        self.assertEqual(manifest.read_text(),json.dumps(self.manifest))


if __name__=='__main__':unittest.main()
