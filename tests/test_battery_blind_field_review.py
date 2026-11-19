"""Prospective blinded review pilot: synthetic safety and source linkage only."""
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'research'/'battery_curve_audit'))
import integrated_customer_gate as gate
import blind_field_review as blind


def table(path):
    with path.open(newline='', encoding='utf-8') as fp:
        return list(csv.DictReader(fp))


def write_table(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as fp:
        writer=csv.DictWriter(fp,fieldnames=fields)
        writer.writeheader();writer.writerows(rows)


class BlindedFieldReviewTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        names='ABCD'
        manifest={'schema':'cano.battery.customer-files.v1','files':[]}
        for i,cell in enumerate(names):
            value=4.20-i*.30
            (self.root/(cell+'.csv')).write_text(
                'Timestamp_1 [h],DC1 [V]\n' + '\n'.join(
                    f'{t},{value-t*.003:.5f}' for t in range(120))+'\n',encoding='utf-8')
            manifest['files'].append({'path':cell+'.csv','cell':cell,'mode':'dchg'})
        self.manifest=self.root/'manifest.json'
        self.manifest.write_text(json.dumps(manifest),encoding='utf-8')
        self.audit=self.root/'audit.json'
        source=gate.integrated_check(manifest,self.root)
        self.assertEqual(source['decision'],'PASS_SCREEN_ONLY')
        self.audit.write_text(json.dumps(source,sort_keys=True),encoding='utf-8')
        part={x['cell']:x['partition'] for x in source['split']['assignments']}
        self.cells=self.root/'cells.csv'
        write_table(self.cells,['cell','device','batch','campaign','partition'],[
            {'cell':c,'device':'DEV'+c,'batch':'B'+c,'campaign':'C'+c,'partition':part[c]} for c in names])
        self.pairs=self.root/'private-predictions.csv'
        pairs=[]
        for i,c in enumerate(names):
            for d in names[i+1:]:
                pairs.append({'a':c,'b':d,'flagged':'false'})
        write_table(self.pairs,['a','b','flagged'],pairs)
        self.frame=self.root/'frame.json'
        frame={'schema':'cano.battery.field-intake-frame.v1',
               'site_authorization':{'permitted':True,'reference':'SYNTHETIC_SITE_NOT_REAL_AUTHORIZATION'},
               'audit_receipt_sha256':hashlib.sha256(self.audit.read_bytes()).hexdigest(),
               'screened_pair_count':6,'screened_flagged_count':0}
        self.frame.write_text(json.dumps(frame),encoding='utf-8')
        self.form_a=self.root/'technician_one.csv'
        self.form_b=self.root/'technician_two.csv'
        self.seal=self.root/'operator_only.json'
        self.summary=self.root/'private-safe-aggregate.json'
        self.private=self.root/'private-ledger.json'

    def prepare(self,**kw):
        return blind.prepare(self.cells,self.pairs,self.frame,self.audit,
                    self.form_a,self.form_b,self.seal,
                    per_stratum=kw.get('per_stratum',2), secret=kw.get('secret',b'\x19'*32))

    def complete(self,left='independent',right='independent'):
        for form,label in ((self.form_a,left),(self.form_b,right)):
            rows=table(form)
            for row in rows:row['verdict']=label
            write_table(form,['pair_id','a','b','verdict'],rows)

    def finalize(self,**kw):
        return blind.finalize(self.manifest,self.root,self.audit,self.cells,self.pairs,
                              self.frame,self.form_a,self.form_b,self.seal,self.summary,
                              reviewer_a_id=kw.get('reviewer_a_id','TECH_A'),
                              reviewer_b_id=kw.get('reviewer_b_id','TECH_B'),
                              private_ledger_path=kw.get('private_ledger_path'))

    def test_three_cli_stages_work_end_to_end_on_synthetic_inputs(self):
        pair=self.root/'generated-pairs.csv';frame=self.root/'generated-frame.json'
        self.assertEqual(blind.main(['screen','--manifest',str(self.manifest),'--root',str(self.root),
             '--audit-report',str(self.audit),'--cells',str(self.cells),
             '--pairs-out',str(pair),'--frame-out',str(frame)]),0)
        self.pairs.write_bytes(pair.read_bytes())
        meta=json.loads(frame.read_text())
        meta['site_authorization']={'permitted':True,'reference':'SYNTHETIC_SITE_NOT_REAL_AUTHORIZATION'}
        self.frame.write_text(json.dumps(meta))
        self.assertEqual(blind.main(['prepare','--cells',str(self.cells),'--pairs',str(self.pairs),
             '--frame',str(self.frame),'--audit-report',str(self.audit),
             '--reviewer-a-form',str(self.form_a),'--reviewer-b-form',str(self.form_b),
             '--operator-seal',str(self.seal),'--per-stratum','2']),0)
        self.complete()
        self.assertEqual(blind.main(['finalize','--manifest',str(self.manifest),'--root',str(self.root),
             '--audit-report',str(self.audit),'--cells',str(self.cells),'--pairs',str(self.pairs),
             '--frame',str(self.frame),'--reviewer-a-form',str(self.form_a),
             '--reviewer-b-form',str(self.form_b),'--operator-seal',str(self.seal),
             '--summary',str(self.summary),'--reviewer-a-id','TECH_A','--reviewer-b-id','TECH_B']),0)
        self.assertEqual(json.loads(self.summary.read_text())['decision'],'PILOT_ONLY_NOT_CERTIFIED')

    def test_verified_source_screen_generator_reproduces_all_clean_pairs(self):
        frame_out=self.root/'new-private-frame.json'
        screen_out=self.root/'new-private-pairs.csv'
        result=blind.generate_screen(self.manifest,self.root,self.audit,self.cells,
                                     screen_out,frame_out)
        self.assertEqual(result['screened_pair_count'],6)
        self.assertEqual(result['screened_flagged_count'],0)
        self.assertEqual(table(screen_out),table(self.pairs))
        self.assertFalse(json.loads(frame_out.read_text())['site_authorization']['permitted'])

    def test_source_exact_duplicate_creates_candidate_not_field_certificate(self):
        (self.root/'B.csv').write_text((self.root/'A.csv').read_text())
        manifest=json.loads(self.manifest.read_text())
        source=gate.integrated_check(manifest,self.root)
        self.assertEqual(source['decision'],'REVIEW_REQUIRED')
        self.audit.write_text(json.dumps(source,sort_keys=True),encoding='utf-8')
        self.write_cells_from_report(source)
        pair_out=self.root/'verified-pairs.csv';frame_out=self.root/'template-frame.json'
        result=blind.generate_screen(self.manifest,self.root,self.audit,self.cells,pair_out,frame_out)
        self.assertGreater(result['screened_flagged_count'],0)
        self.pairs.write_bytes(pair_out.read_bytes())
        frm=json.loads(frame_out.read_text());frm['site_authorization']={
            'permitted':True,'reference':'SYNTHETIC_SITE_NOT_REAL_AUTHORIZATION'}
        self.frame.write_text(json.dumps(frm))
        self.prepare();self.complete()
        bound=self.finalize()
        self.assertEqual(bound['decision'],'BLOCK_AUDIT_REVIEW')
        self.assertEqual(bound['field_acceptance'],'NOT_ESTABLISHED')

    def write_cells_from_report(self,report):
        part={x['cell']:x['partition'] for x in report['split']['assignments']}
        rows=[{'cell':c,'device':'DEV'+c,'batch':'B'+c,'campaign':'C'+c,
               'partition':part[c]} for c in 'ABCD']
        write_table(self.cells,['cell','device','batch','campaign','partition'],rows)

    def test_fake_algorithm_flag_is_rejected_by_real_recomputed_screen(self):
        rows=table(self.pairs);rows[0]['flagged']='true'
        write_table(self.pairs,['a','b','flagged'],rows)
        frame=json.loads(self.frame.read_text());frame['screened_flagged_count']=1
        self.frame.write_text(json.dumps(frame))
        self.prepare();self.complete()
        with self.assertRaisesRegex(ValueError,'screen|predic|source|model'):
            self.finalize()
        self.assertFalse(self.summary.exists())

    def test_short_unscreened_source_cannot_generate_false_clean_pair_screen(self):
        (self.root/'A.csv').write_text('Timestamp_1 [h],DC1 [V]\n0,4.2\n1,4.1\n')
        manifest=json.loads(self.manifest.read_text())
        source=gate.integrated_check(manifest,self.root)
        self.audit.write_text(json.dumps(source,sort_keys=True),encoding='utf-8')
        self.write_cells_from_report(source)
        with self.assertRaisesRegex(ValueError,'unscreened|short|flat'):
            blind.generate_screen(self.manifest,self.root,self.audit,self.cells,
                                  self.root/'out-pair.csv',self.root/'out-frame.json')

    def test_prepare_never_exposes_model_flags_to_reviewers(self):
        result=self.prepare()
        self.assertEqual(result['selected_flagged'],0)
        self.assertEqual(result['selected_clear'],2)
        a=table(self.form_a);b=table(self.form_b)
        self.assertEqual(len(a),2)
        self.assertEqual({r['pair_id'] for r in a},{r['pair_id'] for r in b})
        self.assertTrue(all(r['verdict']=='' for r in a+b))
        for path in (self.form_a,self.form_b):
            self.assertEqual(list(a[0]),['pair_id','a','b','verdict'])
            content=path.read_text()
            for private in ('flagged','true','false','SYNTHETIC_SITE_NOT_REAL_AUTHORIZATION','audit_receipt_sha256'):
                self.assertNotIn(private,content)
            if os.name=='posix':self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertTrue(all(isinstance(row['flagged'],bool) for row in json.loads(self.seal.read_text())['sampled']))
        self.assertEqual(len({r['pair_id'] for r in a}),2)

    def test_prepare_is_deterministic_with_same_private_random_key(self):
        self.prepare()
        sample=json.loads(self.seal.read_text())['sampled']
        another=self.root/'next'
        another.mkdir()
        blind.prepare(self.cells,self.pairs,self.frame,self.audit,
            another/'a.csv',another/'b.csv',another/'seal.json',
            per_stratum=2,secret=b'\x19'*32)
        self.assertEqual(sample,json.loads((another/'seal.json').read_text())['sampled'])
        self.assertEqual(table(self.form_a),table(another/'a.csv'))

    def test_reviewer_forms_have_different_nonflag_order(self):
        self.prepare(per_stratum=3)
        self.assertNotEqual([x['pair_id'] for x in table(self.form_a)],
                            [x['pair_id'] for x in table(self.form_b)])

    def test_bad_pair_frame_count_rejected_without_writing(self):
        q=json.loads(self.frame.read_text());q['screened_pair_count']=5
        self.frame.write_text(json.dumps(q))
        with self.assertRaisesRegex(ValueError,'frame|count|screened'):
            self.prepare()
        self.assertFalse(self.form_a.exists())

    def test_duplicate_reversed_pair_rejected(self):
        rows=table(self.pairs);rows[-1]={'a':'B','b':'A','flagged':'false'}
        write_table(self.pairs,['a','b','flagged'],rows)
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.prepare()

    def test_unknown_cell_in_pair_rejected(self):
        rows=table(self.pairs);rows[-1]['b']='NOT_A_CELL'
        write_table(self.pairs,['a','b','flagged'],rows)
        with self.assertRaisesRegex(ValueError,'unknown'):
            self.prepare()

    def test_flag_token_not_guessed(self):
        rows=table(self.pairs);rows[0]['flagged']='YES'
        write_table(self.pairs,['a','b','flagged'],rows)
        with self.assertRaisesRegex(ValueError,'flagged'):
            self.prepare()

    def test_prepare_refuses_existing_output_and_does_not_clobber(self):
        self.form_a.write_bytes(b'PERSONAL-IRREPLACEABLE')
        with self.assertRaisesRegex(ValueError,'existing|overwrite'):
            self.prepare()
        self.assertEqual(self.form_a.read_bytes(),b'PERSONAL-IRREPLACEABLE')
        self.assertFalse(self.form_b.exists())

    def test_prepare_refuses_overwriting_input(self):
        before=self.pairs.read_bytes()
        with self.assertRaisesRegex(ValueError,'collide|source|input'):
            blind.prepare(self.cells,self.pairs,self.frame,self.audit,
                          self.pairs,self.form_b,self.seal,secret=b'\x11'*32)
        self.assertEqual(self.pairs.read_bytes(),before)

    def test_only_clear_stratum_has_no_precision_claim(self):
        rows=table(self.pairs)
        for row in rows:row['flagged']='false'
        write_table(self.pairs,['a','b','flagged'],rows)
        frame=json.loads(self.frame.read_text());frame['screened_flagged_count']=0
        self.frame.write_text(json.dumps(frame))
        q=self.prepare(per_stratum=3)
        self.assertEqual(q['selected_flagged'],0)
        self.assertEqual(q['selected_clear'],3)

    def test_valid_completed_forms_bind_to_actual_raw_source_not_certified(self):
        self.prepare();self.complete()
        result=self.finalize()
        self.assertEqual(result['decision'],'PILOT_ONLY_NOT_CERTIFIED')
        self.assertEqual(result['field_acceptance'],'NOT_ESTABLISHED')
        self.assertTrue(result['source_recalculated_and_matched'])
        self.assertTrue(result['receipt_and_partitions_bound'])
        self.assertEqual(result['field_counts']['reviewed_pair_count'],2)
        self.assertEqual(result['field_counts']['consensus']['fp'],0)
        self.assertEqual(result['field_counts']['consensus']['tn'],2)
        self.assertNotIn('TECH_A',self.summary.read_text())
        self.assertNotIn('SYNTHETIC_SITE_NOT_REAL_AUTHORIZATION',self.summary.read_text())
        self.assertNotIn('audit_receipt_sha256',self.summary.read_text())

    def test_source_csv_tampering_rejected_even_with_completed_forms(self):
        self.prepare();self.complete()
        (self.root/'A.csv').write_text((self.root/'A.csv').read_text().replace('4.20000','4.10000'))
        with self.assertRaisesRegex(ValueError,'source|audit|mismatch|changed'):
            self.finalize()
        self.assertFalse(self.summary.exists())

    def test_operator_pairs_tampered_after_sampling_rejected(self):
        self.prepare();self.complete()
        self.pairs.write_text(self.pairs.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'pair|changed|digest|hash'):
            self.finalize()
        self.assertFalse(self.summary.exists())

    def test_seal_cannot_relabel_original_model_predictions(self):
        self.prepare();self.complete()
        obj=json.loads(self.seal.read_text())
        obj['sampled'][0]['flagged']=not obj['sampled'][0]['flagged']
        obj['selected_flagged']=sum(r['flagged'] for r in obj['sampled'])
        obj['selected_clear']=len(obj['sampled'])-obj['selected_flagged']
        self.seal.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'prediction|screen|pair|seal'):
            self.finalize()
        self.assertFalse(self.summary.exists())

    def test_unreviewed_frame_does_not_create_an_estimated_error_rate(self):
        rows=table(self.pairs)
        for row in rows:row['flagged']='false'
        write_table(self.pairs,['a','b','flagged'],rows)
        frame=json.loads(self.frame.read_text());frame['screened_flagged_count']=0
        self.frame.write_text(json.dumps(frame))
        self.prepare();self.complete()
        result=self.finalize()
        self.assertIsNone(result['field_counts']['rates']['precision'])
        self.assertEqual(result['field_acceptance'],'NOT_ESTABLISHED')

    def test_review_form_pair_id_must_match_sealed_sampling(self):
        self.prepare();self.complete()
        rows=table(self.form_b);rows[0]['pair_id']='REPLACED'
        write_table(self.form_b,['pair_id','a','b','verdict'],rows)
        with self.assertRaisesRegex(ValueError,'form|pair|roster|seal'):
            self.finalize()
        self.assertFalse(self.summary.exists())

    def test_missing_technician_verdict_not_silently_inferred(self):
        self.prepare();self.complete()
        rows=table(self.form_a);rows[0]['verdict']=''
        write_table(self.form_a,['pair_id','a','b','verdict'],rows)
        with self.assertRaisesRegex(ValueError,'form|verdict|CSV'):
            self.finalize()
        self.assertFalse(self.summary.exists())

    def test_two_reviewers_cannot_be_same_identity(self):
        self.prepare();self.complete()
        with self.assertRaisesRegex(ValueError,'reviewer|distinct'):
            self.finalize(reviewer_b_id='TECH_A')
        self.assertFalse(self.summary.exists())

    def test_final_output_cannot_overwrite_any_source_or_operator_file(self):
        self.prepare();self.complete()
        for original in (self.manifest,self.audit,self.cells,self.pairs,self.frame,self.form_a,self.form_b,self.seal,self.root/'A.csv'):
            before=original.read_bytes()
            with self.assertRaisesRegex(ValueError,'output|source|input|collide|overwrite'):
                blind.finalize(self.manifest,self.root,self.audit,self.cells,self.pairs,
                    self.frame,self.form_a,self.form_b,self.seal,original,
                    reviewer_a_id='TECH_A',reviewer_b_id='TECH_B')
            self.assertEqual(original.read_bytes(),before)

    def test_exclusive_private_ledger_opt_in(self):
        self.prepare();self.complete()
        self.finalize(private_ledger_path=self.private)
        self.assertTrue(self.private.is_file())
        self.assertNotIn('TECH_A',self.summary.read_text())
        self.assertIn('TECH_A',self.private.read_text())
        if os.name=='posix':self.assertEqual(self.private.stat().st_mode&0o777,0o600)


if __name__=='__main__':unittest.main()
