"""Adversarial checks for published aggregate mechanical/electrical comparisons."""
import csv
from decimal import Decimal as D
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

P=Path(__file__).resolve().parent
if P.name == 'tests':
 P=P.parent/'research'/'battery_curve_audit'
spec=importlib.util.spec_from_file_location('audit',P/'impact_published_protocol_crosscheck.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
CSV=P/'impact_wei2025_publisher_group.csv'

class PaperCheck(unittest.TestCase):
 def test_source_pin(self):
  self.assertEqual(hashlib.sha256(CSV.read_bytes()).hexdigest(),audit.PIN)
 def test_reproduce_all_three_group_metrics(self):
  o=audit.run(CSV.read_bytes()); self.assertEqual([r['energy_group_J'] for r in o['impact_groups']],[3,5,7]);self.assertFalse(o['production_release_allowed'])
 def test_nominal_not_measured_fresh_baseline(self):
  o=audit.run(CSV.read_bytes());self.assertFalse(o['nominal_850mAh_falls_inside_conditional_common_baseline']);self.assertTrue(o['common_reference_baseline_math_possible'])
  lo,hi=map(D,o['conditional_common_reference_baseline_interval_mAh']);self.assertTrue(D('825')<lo<hi<D('831'))
 def test_low_capacity_loss_can_hide_big_mechanical_loss(self):
  r=audit.run(CSV.read_bytes())['impact_groups'][0];self.assertTrue(r['substantial_mechanical_loss_even_with_small_electrical_loss_observed']);self.assertGreater(D(r['derived_failure_deformation_energy_loss_percent']),39)
 def test_impact_kinetic_energy_independent_arithmetic(self):
  groups=audit.run(CSV.read_bytes())['impact_groups'];self.assertTrue(all(abs(D(x['difference_from_nominal_energy_J'])) <D('.02') for x in groups))
 def test_source_tamper_rejected(self):
  with self.assertRaisesRegex(ValueError,'sha256'):audit.run(CSV.read_bytes().replace(b'99.4',b'98.4'))
 def test_unverified_baseline_claim_not_inferred(self):
  o=audit.run(CSV.read_bytes());self.assertTrue(o['capacity_baseline_math_conditional_on_common_baseline_and_display_rounding']);self.assertFalse(o['exact_mechanical_electrical_sample_identity_verified'])
 def test_no_bayreuth_merger_or_certification(self):
  o=audit.run(CSV.read_bytes());self.assertFalse(o['bayreuth_aging_cells_paired_with_impact_cells']);self.assertFalse(o['dated_instrument_calibration_verified']);self.assertFalse(o['field_FPR_FNR_established'])
 def test_rounding_envelope_strict_invalid_inputs(self):
  for loss,pct in ((D('0'),D('2')),(D('2'),D('0')),(D('2'),D('NaN')),(D('2'),D('100'))):
   with self.subTest(loss=loss,pct=pct),self.assertRaises(ValueError):audit.inferred_reference_interval(loss,pct)
 def test_real_rounding_interval_consistent(self):
  lo,hi=audit.inferred_reference_interval(D('52.67'),D('6.4'))
  self.assertLess(lo,D('828'));self.assertGreater(hi,D('828'))
 def test_main_protects_existing_result(self):
  with tempfile.TemporaryDirectory() as td:
   target=Path(td)/'out.json';target.write_text('{}');self.assertEqual(audit.main([str(CSV),str(target)]),2);self.assertEqual(target.read_text(),'{}')
 def test_main_reproducible_file(self):
  with tempfile.TemporaryDirectory() as td:
   dest=Path(td)/'out.json';self.assertEqual(audit.main([str(CSV),str(dest)]),0)
   data=json.loads(dest.read_text());self.assertEqual(data['reported_impact_groups'],3);self.assertFalse(data['original_individual_cell_rows_retrieved'])
if __name__=='__main__':unittest.main()