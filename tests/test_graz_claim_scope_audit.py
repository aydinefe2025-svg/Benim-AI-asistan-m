"""Original-source proof scope + no synthetic release substitution."""
import json
import unittest
from pathlib import Path
from research.battery_curve_audit import graz_claim_scope_audit as audit
BASE=Path(__file__).resolve().parents[1]/'real_source_refs'
SAMPLE=BASE/'GRAZ_FIVE_ORIGINAL_SP_ELECTRICAL_ALIGNMENT_20261123.json'
IDENT=BASE/'GRAZ_5_HUCRE_ELEKTRIK_KAYIT_KIMLIGI_DENETIMI_20261123.json'

class OriginalReleaseLedgerTests(unittest.TestCase):
    def test_two_original_derived_evidence_proofs(self):
        d=audit.build_claim_ledger(SAMPLE.read_bytes(),IDENT.read_bytes())
        self.assertEqual(d['real_original_sensor_rows'],234021)
        self.assertEqual(d['timestamp_proximity_within_one_second'],204673)
        self.assertEqual(d['actual_independent_hardware_certificates'],0)
        self.assertFalse(d['physical_production_release_allowed'])
        self.assertTrue(d['original_derived_evidence_integrity_pass'])
        self.assertFalse(d['scientific_claims']['calibrated_capacity_Ah']['verified'])
        self.assertFalse(d['scientific_claims']['cross_instrument_clock_synchronization']['verified'])
        self.assertFalse(d['scientific_claims']['dynamic_impact_safety']['verified'])
        self.assertFalse(d['scientific_claims']['causal_preload_effect']['verified'])
    def test_any_changed_source_byte_fails_closed(self):
        b=SAMPLE.read_bytes()
        with self.assertRaises(ValueError):audit.build_claim_ledger(b+b' ',IDENT.read_bytes())
    def test_untrusted_assertion_of_calibration_fails_closed(self):
        d=json.loads(SAMPLE.read_text());d['guardrails']['independent_instrument_clock_calibration_verified']=True
        with self.assertRaises(ValueError):audit.build_claim_ledger(json.dumps(d).encode(),IDENT.read_bytes())
    def test_missing_either_source_fails_closed(self):
        with self.assertRaises(ValueError):audit.build_claim_ledger(SAMPLE.read_bytes(),b'')
    def test_forged_identity_document_fails_closed(self):
        b=IDENT.read_bytes();with_a=b.replace(b'"original_electrical_records"',b'"fake_electrical_records"')
        with self.assertRaises(ValueError):audit.build_claim_ledger(SAMPLE.read_bytes(),with_a)

if __name__=='__main__':unittest.main()