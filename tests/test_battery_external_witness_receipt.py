"""Synthetic-only, separately provisioned witness-key protocol regression tests."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'/'battery_curve_audit'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import external_witness_receipt as witness


class ExternalWitnessReceiptTests(unittest.TestCase):
    def setUp(self):
        from test_battery_blind_field_review import BlindedFieldReviewTests
        fixture=BlindedFieldReviewTests('test_valid_completed_forms_bind_to_actual_raw_source_not_certified')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fx=fixture
        fixture.prepare()
        fixture.complete()
        fixture.finalize()
        extra=tempfile.TemporaryDirectory()
        self.addCleanup(extra.cleanup)
        self.witness_dir=Path(extra.name)
        self.keypath=self.witness_dir/'external-witness.secret'
        self.key=b'w'*32
        self.keypath.write_bytes(self.key)
        if os.name == 'posix':self.keypath.chmod(0o600)
        self.fingerprint=hashlib.sha256(self.key).hexdigest()
        self.inputs={
            'manifest':fixture.manifest,'audit':fixture.audit,
            'cells':fixture.cells,'pairs':fixture.pairs,'frame':fixture.frame,
            'form_a':fixture.form_a,'form_b':fixture.form_b,'seal':fixture.seal,
            'public_summary':fixture.summary
        }
        self.options={
            'files':self.inputs,'root':fixture.root,'operator_key':Path(str(fixture.seal)+'.key'),
            'reviewer_a_id':'TECH_A','reviewer_b_id':'TECH_B'
        }
        self.nonce='0123456789abcdef0123456789abcdef'
        self.request=witness.build_request(**self.options,nonce=self.nonce)
        self.receipt=witness.endorse(self.request,self.key)

    def verified(self, request=None, signed=None, key=None, pin=None):
        return witness.verify(request or self.request,signed or self.receipt,
            key or self.key, pin or self.fingerprint,**self.options)

    def test_independently_pinned_witness_record_matches_sources_but_does_not_certify_site(self):
        out=self.verified()
        self.assertEqual(out['decision'],'WITNESS_KEYED_INTEGRITY_MATCH_ONLY')
        self.assertEqual(out['field_acceptance'],'NOT_ESTABLISHED')
        self.assertFalse(out['site_authorization_independently_verified'])
        self.assertFalse(out['distinct_reviewer_humans_authenticated'])
        self.assertTrue(out['source_and_blind_review_recomputed'])
        self.assertNotIn('TECH_A',json.dumps(out))
        self.assertNotIn('audit_receipt_sha256',json.dumps(out))
        self.assertNotIn(self.fingerprint,json.dumps(out))

    def test_key_not_embedded_in_request_or_endorsement(self):
        data=(witness._canonical(self.request)+witness._canonical(self.receipt))
        self.assertNotIn(self.key,data)
        self.assertNotIn('site_authorization',json.dumps(self.receipt))

    def test_unpinned_or_forged_witness_key_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'trust anchor'):
            self.verified(key=b'z'*32)
        with self.assertRaisesRegex(ValueError,'fingerprint'):
            self.verified(pin='not-from-independent-custodian')
        altered=copy.deepcopy(self.receipt)
        altered['mac']='0'*64
        with self.assertRaisesRegex(ValueError,'endorsement'):
            self.verified(signed=altered)

    def test_operator_and_witness_must_have_separate_secrets(self):
        operator=Path(str(self.fx.seal)+'.key').read_bytes()
        with self.assertRaisesRegex(ValueError,'share secret'):
            self.verified(key=operator,pin=hashlib.sha256(operator).hexdigest(),
                signed=witness.endorse(self.request,operator))

    def test_changed_raw_time_voltage_csv_fails_complete_reaudit(self):
        p=self.fx.root/'A.csv'
        p.write_text(p.read_text().replace('4.20000','4.10000'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'source|audit|mismatch|changed'):
            self.verified()

    def test_changed_blind_reviewer_answer_fails_snapshot_even_if_source_intact(self):
        from test_battery_blind_field_review import table,write_table
        rows=table(self.fx.form_a)
        rows[0]['verdict']='linked'
        write_table(self.fx.form_a,['pair_id','a','b','verdict'],rows)
        with self.assertRaisesRegex(ValueError,'snapshot|reproducible'):
            self.verified()

    def test_changed_source_authorization_reference_fails_before_witness(self):
        p=self.fx.frame
        frame=json.loads(p.read_text())
        frame['site_authorization']['reference']='ANOTHER_UNCHECKED_AUTHORITY'
        p.write_text(json.dumps(frame))
        with self.assertRaisesRegex(ValueError,'hash|mismatch|source'):
            self.verified()

    def test_changed_private_seal_fails_even_with_new_matching_json_receipt(self):
        o=json.loads(self.fx.seal.read_text())
        o['selection_design']='edited'
        self.fx.seal.write_text(json.dumps(o),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'authentication|tamper'):
            self.verified()

    def test_operator_cannot_replace_receipt_or_source_commitment(self):
        r=copy.deepcopy(self.request)
        r['evidence_sha256']['form_a']='a'*64
        with self.assertRaisesRegex(ValueError,'endorsement'):
            self.verified(request=r)
        receipt=witness.endorse(r,self.key)
        with self.assertRaisesRegex(ValueError,'snapshot changed'):
            self.verified(request=r,signed=receipt)

    def test_no_overwrite_private_source_or_existing_report(self):
        path=self.fx.root/'proof.json'
        path.write_bytes(b'DO NOT OVERWRITE')
        with self.assertRaisesRegex(ValueError,'collides'):
            witness._atomic_new(path,b'synthetic',protected=self.inputs.values())
        self.assertEqual(path.read_bytes(),b'DO NOT OVERWRITE')
        with self.assertRaisesRegex(ValueError,'collides'):
            witness._atomic_new(self.fx.summary,b'synthetic',protected=self.inputs.values())

    def test_symlink_or_wrong_permissions_witness_key_denied(self):
        link=self.witness_dir/'witness-link.key'
        try:link.symlink_to(self.keypath)
        except (OSError,NotImplementedError):return
        with self.assertRaisesRegex(ValueError,'linked'):
            witness._load_key(link)
        if os.name=='posix':
            self.keypath.chmod(0o644)
            with self.assertRaisesRegex(ValueError,'permissions'):
                witness._load_key(self.keypath)

    def test_complete_cli_prepare_endorse_verify_and_no_key_written_in_output(self):
        def common():
            args=[]
            for name in witness.FILE_KEYS:
                args.extend(('--'+name.replace('_','-'),str(self.inputs[name])))
            args+=['--root',str(self.fx.root),'--operator-key',str(self.options['operator_key']),
                   '--reviewer-a-id','TECH_A','--reviewer-b-id','TECH_B']
            return args
        request=self.fx.root/'challenge.json'
        endorse=self.fx.root/'endorsement.json'
        output=self.fx.root/'public-result.json'
        self.assertEqual(witness.main(['prepare',*common(),'--request',str(request)]),0)
        self.assertEqual(witness.main(['endorse','--request',str(request),'--witness-key',str(self.keypath),
                                      '--endorsement',str(endorse)]),0)
        self.assertEqual(witness.main(['verify',*common(),'--request',str(request),
                                      '--endorsement',str(endorse),'--witness-key',str(self.keypath),
                                      '--expected-witness-key-sha256',self.fingerprint,
                                      '--output',str(output)]),0)
        out=json.loads(output.read_text())
        self.assertEqual(out['decision'],'WITNESS_KEYED_INTEGRITY_MATCH_ONLY')
        self.assertEqual(out['field_acceptance'],'NOT_ESTABLISHED')
        self.assertNotIn(self.fingerprint,output.read_text())
        self.assertEqual(witness.main(['verify',*common(),'--request',str(request),
                                      '--endorsement',str(endorse),'--witness-key',str(self.keypath),
                                      '--expected-witness-key-sha256',self.fingerprint,
                                      '--output',str(output)]),2)
        if os.name=='posix':self.assertEqual(output.stat().st_mode&0o777,0o600)


if __name__=='__main__':unittest.main()
