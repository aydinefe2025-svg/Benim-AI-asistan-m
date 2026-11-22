import copy
import json
import math
import unittest
from pathlib import Path
try:
    from research.battery_curve_audit.instrument_family_accuracy_envelope import run
except ModuleNotFoundError:
    from instrument_family_accuracy_envelope import run
DIR=Path(__file__).resolve().parent
if not (DIR/'verified_source_derived_minimal_ledger.json').exists():
    DIR=DIR.parent/'research'/'battery_curve_audit'
class TestAccuracyEnvelope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger=json.loads((DIR/'verified_source_derived_minimal_ledger.json').read_text())
        cls.scenarios=json.loads((DIR/'instrument_family_assumptions.json').read_text())
    def test_source_numbers_preserved(self):
        r=run(self.ledger,self.scenarios)
        self.assertEqual(r['source_cell_count'],4)
        self.assertEqual(r['condition_pair_count'],12)
        self.assertEqual([x['observed_AT_minus_ET_discharge_capacity_mAh'] for x in r['capacity_current_only_scenarios']],[4.722248,3.422486,11.352585,9.29959])
    def test_legacy_family_2channel_bound(self):
        r=run(self.ledger,self.scenarios)
        self.assertEqual(r['cells_exceeding_current_only_catalog_scenario'],2)
        self.assertAlmostEqual(r['capacity_current_only_scenarios'][2]['hypothetical_max_ET_AT_current_error_only_mAh'],4.399662,places=6)
        self.assertAlmostEqual(r['capacity_current_only_scenarios'][3]['hypothetical_max_ET_AT_current_error_only_mAh'],4.473955,places=6)
    def test_XCTS_scenario_not_overclaimed(self):
        r=run(self.ledger,self.scenarios)
        self.assertFalse(r['capacity_current_only_scenarios'][0]['observed_exceeds_hypothetical_error_only_bound'])
        self.assertFalse(r['capacity_current_only_scenarios'][1]['observed_exceeds_hypothetical_error_only_bound'])
    def test_voltage_only_bound_not_statistical_CI(self):
        r=run(self.ledger,self.scenarios)
        self.assertEqual(r['dcir_condition_pairs_below_voltage_only_hypothetical_scenario'],12)
        self.assertFalse(r['uncertainty_95pct_confidence_interval_established'])
        self.assertTrue(0.81<r['dcir_voltage_only_scenarios'][0]['hypothetical_four_voltage_reading_deltaR_max_mOhm']<0.83)
    def test_never_claim_certificate_or_product_release(self):
        r=run(self.ledger,self.scenarios)
        for k in ('published_specs_are_serial_number_specific_calibration',
                  'source_2021_2022_instrument_calibration_obtained',
                  'physical_aging_causality_established','commercial_production_release_allowed'):
            self.assertIs(r[k],False)
    def test_reject_missing_source_provenance(self):
        x=copy.deepcopy(self.ledger);x['source_evidence_refs'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):run(x,self.scenarios)
    def test_reject_duplicate_original_cell(self):
        x=copy.deepcopy(self.ledger);x['source_cells'][1]['source_cell']=x['source_cells'][0]['source_cell']
        with self.assertRaises(ValueError):run(x,self.scenarios)
    def test_reject_missing_condition(self):
        x=copy.deepcopy(self.ledger);x['pulse_condition_pairs'].pop()
        with self.assertRaises(ValueError):run(x,self.scenarios)
    def test_reject_fake_calibration(self):
        x=copy.deepcopy(self.scenarios);x['not_a_calibration_certificate']=False
        with self.assertRaises(ValueError):run(self.ledger,x)
    def test_reject_negative_accuracy(self):
        x=copy.deepcopy(self.scenarios);x['family_current_accuracy_scenarios']['CTS_legacy_two_channels']['assumed_abs_current_mA_each_channel']=-1
        with self.assertRaises(ValueError):run(self.ledger,x)
    def test_reject_changed_CTSpair(self):
        x=copy.deepcopy(self.scenarios);x['family_current_accuracy_scenarios']['CTS_legacy_two_channels']['parallel_channels']=1
        with self.assertRaises(ValueError):run(self.ledger,x)
    def test_reject_nonfinite_pulse(self):
        x=copy.deepcopy(self.ledger);x['pulse_condition_pairs'][0]['corrected_DCiR_AT_minus_ET_mOhm']=float('nan')
        with self.assertRaises(ValueError):run(x,self.scenarios)
    def test_exact_equal_replays(self):
        self.assertEqual(run(self.ledger,self.scenarios),run(copy.deepcopy(self.ledger),copy.deepcopy(self.scenarios)))
if __name__=='__main__':unittest.main()