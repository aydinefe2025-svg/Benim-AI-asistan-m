"""Offline customer-site intake tests using *synthetic* metadata/reviews only."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / 'research' / 'battery_curve_audit'))
import field_pilot_csv_intake as intake


class FieldCSVIntakeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cells = self.root / 'cells.csv'
        self.reviews = self.root / 'reviews.csv'
        self.frame = self.root / 'frame.json'
        self.cells.write_text('cell,device,batch,campaign,partition\nA,dA,bA,pA,train\nB,dB,bB,pB,validation\nC,dC,bC,pC,test\nD,dD,bD,pD,train\n', encoding='utf-8')
        self.reviews.write_text('a,b,flagged,reviewer_a_id,reviewer_a_verdict,reviewer_b_id,reviewer_b_verdict\nA,B,true,t1,linked,t2,linked\nA,C,false,t1,independent,t2,independent\nB,C,false,t1,linked,t2,linked\n', encoding='utf-8')
        self.frame.write_text(json.dumps({'schema':'cano.battery.field-intake-frame.v1',
            'site_authorization':{'permitted':True,'reference':'local-only-attestation'},
            'audit_receipt_sha256':'a'*64,'screened_pair_count':6,
            'screened_flagged_count':1}), encoding='utf-8')

    def run_intake(self):
        return intake.evaluate(self.cells, self.reviews, self.frame)

    def test_uses_existing_gate_for_metrics_and_provenance_block(self):
        result, ledger = self.run_intake()
        self.assertEqual(result['decision'],'BLOCK_PROVENANCE_LEAKAGE')
        self.assertEqual(result['consensus'],{'tp':1,'fp':0,'fn':1,'tn':1})
        self.assertEqual(result['reviewed_pair_count'],3)
        self.assertEqual(result['field_acceptance'],'NOT_ESTABLISHED')
        self.assertEqual(ledger['schema'],'cano.battery.field-pilot.v1')

    def test_default_report_redacts_every_private_identifier(self):
        result, _ = self.run_intake()
        payload=json.dumps(result)
        for fragment in ('local-only-attestation', 'dA', 'pA', 't1', 'a'*64, 'cells.csv'):
            self.assertNotIn(fragment,payload)

    def test_allows_valid_clean_metadata_and_no_reviewed_pairs(self):
        self.reviews.write_text('a,b,flagged,reviewer_a_id,reviewer_a_verdict,reviewer_b_id,reviewer_b_verdict\n')
        result,_=self.run_intake()
        self.assertEqual(result['decision'],'PILOT_METRICS_ONLY')
        self.assertIsNone(result['rates']['recall'])
        self.assertEqual(result['reviewed_pair_count'],0)

    def test_duplicate_csv_header_blocked(self):
        self.cells.write_text(self.cells.read_text().replace('cell,device,','cell,cell,'))
        with self.assertRaisesRegex(ValueError,'header'):
            self.run_intake()

    def test_unknown_column_blocked(self):
        self.reviews.write_text(self.reviews.read_text().replace('reviewer_b_verdict','reviewer_b_verdict,untrusted'))
        with self.assertRaisesRegex(ValueError,'header'):
            self.run_intake()

    def test_invalid_boolean_is_not_silently_false(self):
        self.reviews.write_text(self.reviews.read_text().replace('A,B,true,','A,B,yes,'))
        with self.assertRaisesRegex(ValueError,'flagged'):
            self.run_intake()

    def test_repeated_pair_both_orders_blocked(self):
        self.reviews.write_text(self.reviews.read_text()+'B,A,false,t1,independent,t2,independent\n')
        with self.assertRaisesRegex(ValueError,'duplicate unordered'):
            self.run_intake()

    def test_provenance_shared_device_cross_split_is_blocked(self):
        self.cells.write_text(self.cells.read_text().replace('B,dB,bB','B,dA,bB'))
        result,_=self.run_intake()
        self.assertGreater(result['cross_split_metadata_links'],0)

    def test_incomplete_authorization_blocked(self):
        f=json.loads(self.frame.read_text());f['site_authorization']['permitted']=False
        self.frame.write_text(json.dumps(f))
        with self.assertRaisesRegex(ValueError,'authorization'):
            self.run_intake()

    def test_declared_flag_count_inconsistent_with_review_is_blocked(self):
        f=json.loads(self.frame.read_text());f['screened_flagged_count']=0
        self.frame.write_text(json.dumps(f))
        with self.assertRaisesRegex(ValueError,'flagged|frame'):
            self.run_intake()

    def test_no_existing_output_overwrites_even_on_error(self):
        result, ledger=self.run_intake()
        dst=self.root/'summary.json';dst.write_bytes(b'KEEP-ME')
        with self.assertRaisesRegex(ValueError,'existing|overwrite'):
            intake.save(result,dst,inputs=[self.cells,self.reviews,self.frame])
        self.assertEqual(dst.read_bytes(),b'KEEP-ME')

    def test_output_path_cannot_clobber_csv_input(self):
        result,ledger=self.run_intake(); original=self.cells.read_bytes()
        with self.assertRaisesRegex(ValueError,'input|collid'):
            intake.save(result,self.cells,inputs=[self.cells,self.reviews,self.frame])
        self.assertEqual(self.cells.read_bytes(),original)

    def test_private_ledger_only_explicit_opt_in_and_restrictive(self):
        import os, stat
        result,ledger=self.run_intake()
        out=self.root/'summary.json';priv=self.root/'sensitive.json'
        intake.save(result,out,private=ledger,private_path=priv,inputs=[self.cells,self.reviews,self.frame])
        self.assertNotIn('local-only-attestation',out.read_text())
        self.assertIn('local-only-attestation',priv.read_text())
        if os.name=='posix':
            self.assertEqual(stat.S_IMODE(priv.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode),0o600)

    def test_atomic_two_file_preflight_no_existing_private_output(self):
        result,ledger=self.run_intake()
        private=self.root/'private.json';private.write_bytes(b'ORIGINAL')
        public=self.root/'public.json'
        with self.assertRaisesRegex(ValueError,'existing|overwrite'):
            intake.save(result,public,private=ledger,private_path=private,inputs=[self.cells,self.reviews,self.frame])
        self.assertFalse(public.exists());self.assertEqual(private.read_bytes(),b'ORIGINAL')

    def test_frame_json_unknown_key_fails_closed(self):
        f=json.loads(self.frame.read_text());f['invented_certification']='yes'
        self.frame.write_text(json.dumps(f))
        with self.assertRaisesRegex(ValueError,'frame|keys'):
            self.run_intake()

    def test_review_with_embedded_comma_is_parsed_not_split(self):
        self.cells.write_text(self.cells.read_text().replace('A,dA,bA,pA,train','A,"device,one",bA,pA,train'))
        result,_=self.run_intake()
        self.assertEqual(result['cell_count'],4)

    def test_cli_exit_two_on_detected_leak_no_partial_private_file(self):
        report=self.root/'summary.json'
        code=intake.main(['--cells',str(self.cells),'--reviews',str(self.reviews),
                          '--frame',str(self.frame),'--summary',str(report)])
        self.assertEqual(code,2)
        self.assertEqual(json.loads(report.read_text())['decision'],'BLOCK_PROVENANCE_LEAKAGE')

    def test_declared_frame_cannot_exceed_cell_universe(self):
        f=json.loads(self.frame.read_text());f['screened_pair_count']=999
        self.frame.write_text(json.dumps(f))
        with self.assertRaisesRegex(ValueError,'frame'):
            self.run_intake()

if __name__=='__main__':
    unittest.main()
