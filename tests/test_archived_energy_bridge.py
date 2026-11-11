"""Old research must influence CANO choices without misrepresenting evidence."""
from decimal import Decimal
from pathlib import Path
import unittest
import subprocess
import sys
import json

from core.archived_energy_bridge import load_evidence, compare_workload, growth_claim_gate

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'data' / 'cano_research_bridge_evidence.json'


class EnergyEvidenceReuseTests(unittest.TestCase):
    def setUp(self):
        self.evidence = load_evidence(CATALOG_PATH)

    def test_archived_sources_preserve_provenance_and_limitations(self):
        self.assertEqual(self.evidence['schema'], 1)
        self.assertEqual(len(self.evidence['observations']), 4)
        for item in self.evidence['observations']:
            self.assertTrue(item['source'].startswith('https://'))
            self.assertTrue(item['archive'].startswith('https://'))
            self.assertTrue(item['boundary'])

    def test_actual_milliwatt_and_microwatt_units_not_virtual_energy_credits(self):
        outcome = compare_workload(self.evidence, area_cm2='10', standby_mw='0.05',
                                   active_mw='1', active_fraction='0.01', hours=24)
        self.assertEqual(outcome['study_ideal_upper_mw'], '0.6229')
        self.assertEqual(outcome['study_ideal_upper_mwh'], '14.9496')
        self.assertEqual(outcome['load_average_mw'], '0.0595')
        self.assertEqual(outcome['decision'], 'candidate_only_field_measurements_required')
        self.assertEqual(outcome['field_guaranteed_mw'], '0')
        self.assertFalse(outcome['proven_feasible'])

    def test_high_power_compute_not_possible_on_two_archived_peaks_even_ideally(self):
        outcome = compare_workload(self.evidence, area_cm2=10, standby_mw=3000,
                                   active_mw=3000, active_fraction=1, hours=24)
        self.assertEqual(outcome['load_average_mw'], '3000')
        self.assertEqual(outcome['decision'], 'insufficient_even_if_peaks_were_continuous')
        self.assertEqual(outcome['load_mwh'], '72000')

    def test_mechanical_actuation_and_power_transfer_not_double_counted(self):
        outcome = compare_workload(self.evidence, area_cm2=0, standby_mw=1,
                                   active_mw=1, active_fraction=1, hours=1)
        self.assertEqual(outcome['study_ideal_upper_mw'], '0.42')
        self.assertEqual(set(outcome['excluded_from_electric_harvest']),
                         {'thermal_pneumatic_2026', 'tesla_induction_1888'})

    def test_old_failed_adaptation_and_transfer_studies_block_improvement_claims(self):
        outcome = growth_claim_gate(self.evidence)
        self.assertEqual(outcome['decision'], 'do_not_claim_robust_self_improvement')
        self.assertEqual(len(outcome['unpassed_gates']), 2)
        self.assertFalse(outcome['agent_model_weights_updated'])

    def test_corrupt_or_untrusted_numbers_are_rejected(self):
        for field in (dict(area_cm2='-1', standby_mw=1, active_mw=2, active_fraction=0.1, hours=1),
                      dict(area_cm2=10, standby_mw='nan', active_mw=2, active_fraction=0.1, hours=1),
                      dict(area_cm2=10, standby_mw=1, active_mw=2, active_fraction=2, hours=1),
                      dict(area_cm2=10, standby_mw=1, active_mw=2, active_fraction=True, hours=1)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                compare_workload(self.evidence, **field)

    def test_positive_lower_bound_not_invented_from_independent_peak_studies(self):
        outcome = compare_workload(self.evidence, area_cm2=25, standby_mw=0,
                                   active_mw='0.1', active_fraction='0.1', hours='24')
        self.assertEqual(outcome['field_guaranteed_mw'], '0')
        self.assertTrue(outcome['simultaneous_collection_unverified'])
        self.assertFalse(outcome['proven_feasible'])

    def test_existing_seed_lab_demo_consumes_archived_findings(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run([sys.executable, '-m', 'scripts.cano_seed_lab_demo'],
                                   cwd=root, text=True, capture_output=True, check=True)
        report = json.loads(completed.stdout)
        self.assertIn('research_reuse', report)
        self.assertEqual(report['research_reuse']['sensor']['study_ideal_upper_mw'], '0.6229')
        self.assertEqual(report['research_reuse']['compute']['decision'],
                         'insufficient_even_if_peaks_were_continuous')
        self.assertEqual(report['research_reuse']['growth_claim']['unpassed_gates'],
                         ['adaptation_demonstrated', 'compositional_transfer_confirmed'])

    def test_malformed_evidence_cannot_certify_growth(self):
        altered = dict(self.evidence)
        altered['prior_validation'] = {'adaptation_demonstrated': True}
        with self.assertRaises(ValueError):
            growth_claim_gate(altered)


if __name__ == '__main__':
    unittest.main()
