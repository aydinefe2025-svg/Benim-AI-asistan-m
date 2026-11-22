import copy
from decimal import Decimal
import json
import tempfile
from pathlib import Path
import unittest

from research.battery_curve_audit.channel_identifiability_sim import load_observations, simulate, feasible_under_bound

FIXTURE=Path(__file__).resolve().parents[1]/'research'/'battery_curve_audit'/'fixtures'/'k01_k04_k05_nine_source_27_pairs_pinned.json'

class ChannelSimulationTests(unittest.TestCase):
    def test_real_source_count_and_evidence_partition(self):
        raw, rows=load_observations(FIXTURE)
        self.assertEqual(len(rows),27)
        self.assertEqual(len(set((x['cohort'],x['source_file_id']) for x in rows)),9)
    def test_measured_data_does_not_change_in_simulation(self):
        before=FIXTURE.read_bytes();sim=simulate(FIXTURE)
        self.assertEqual(before,FIXTURE.read_bytes())
        self.assertFalse(sim['evidence_partition']['real_waveforms_reintegrated_this_run'])
        self.assertEqual(sim['observed_opposite_or_zero_direction_pairs'],4)
    def test_hypothetical_50_basis_grid(self):
        d=simulate(FIXTURE)
        case=next(x for x in d['hypothetical_scenarios'] if Decimal(x['hypothetical_channel_offset_cap_pp'])==Decimal('0.5'))
        self.assertEqual(case['by_temperature_feasible_of_9'],{'10':4,'23':9,'45':9})
        self.assertEqual(case['source_conditions_feasible_under_ASSUMED_model'],22)
    def test_hypothetical_75_basis_grid(self):
        d=simulate(FIXTURE)
        case=next(x for x in d['hypothetical_scenarios'] if Decimal(x['hypothetical_channel_offset_cap_pp'])==Decimal('.75'))
        self.assertEqual(case['source_conditions_feasible_under_ASSUMED_model'],27)
        self.assertEqual(d['minimum_bound_pp_required_to_fit_all_27_under_model'],.6932)
    def test_noncausal_flags_mandatory(self):
        d=simulate(FIXTURE)
        for k in ('physical_aging_causality_established','temperature_causality_established','instrument_uncertainty_measured','field_FPR_FNR_established','production_release_allowed'):
            self.assertIs(d[k],False)
        self.assertTrue(d['model']['positive_bound_is_user_defined_not_instrument_calibration'])
    def test_zero_bias_cannot_conflate_distinct_channels(self):
        self.assertFalse(feasible_under_bound('-1.3','0.1','0'))
    def test_example_exact_half_gap(self):
        self.assertFalse(feasible_under_bound('-1.3146','.0718','.6931'))
        self.assertTrue(feasible_under_bound('-1.3146','.0718','.6932'))
    def test_strict_latent_negative(self):
        self.assertFalse(feasible_under_bound('0.2','0.3','0.05'))
        self.assertFalse(feasible_under_bound('0','0','0'))
        self.assertTrue(feasible_under_bound('-.1','-.1','0'))
    def test_input_source_sha_is_exact(self):
        import hashlib
        d=simulate(FIXTURE)
        self.assertEqual(d['evidence_partition']['original_source_record_sha256'],hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
    def test_reject_cohort_duplicate(self):
        d=json.loads(FIXTURE.read_text());d['source_results'][1]=copy.deepcopy(d['source_results'][0]);self.assertInvalid(d)
    def test_reject_fake_calibration(self):
        d=json.loads(FIXTURE.read_text());d['instrument_calibration_validated']=True;self.assertInvalid(d)
    def test_reject_fake_phys_custody(self):
        d=json.loads(FIXTURE.read_text());d['physical_custody_authenticated']=True;self.assertInvalid(d)
    def test_reject_relabeling_mixed_measurement(self):
        d=json.loads(FIXTURE.read_text());x=next(x for x in d['source_results'] if x['mixed_or_zero_channel_sign']);x['mixed_or_zero_channel_sign']=False;self.assertInvalid(d)
    def test_reject_incomplete_temperature(self):
        d=json.loads(FIXTURE.read_text());d['source_results'].pop();self.assertInvalid(d)
    def test_reject_nonfinite(self):
        d=json.loads(FIXTURE.read_text());d['source_results'][0]['charge_change_percent']='NaN';self.assertInvalid(d)
    def test_reject_boolean_numeric(self):
        d=json.loads(FIXTURE.read_text());d['source_results'][0]['charge_change_percent']=True;self.assertInvalid(d)
    def test_reject_wrong_schema(self):
        d=json.loads(FIXTURE.read_text());d['schema']='fabricated';self.assertInvalid(d)
    def test_reject_unbounded_scenario(self):
        with self.assertRaises(ValueError):simulate(FIXTURE,['.1','9'])
    def test_reject_negative_b(self):
        with self.assertRaises(ValueError):feasible_under_bound('-1','-1','-0.1')
    def test_reject_b_false_as_source(self):
        with self.assertRaises(ValueError):simulate(FIXTURE,['0.5','0.5'])
    def assertInvalid(self,d):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'tampered.json';p.write_text(json.dumps(d),encoding='utf8')
            with self.assertRaises(ValueError):load_observations(p)

if __name__=='__main__':unittest.main()
