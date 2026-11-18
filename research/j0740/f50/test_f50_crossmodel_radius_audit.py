import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import f50_crossmodel_radius_audit as f
class AuditTests(unittest.TestCase):
 def test_sources_have_distinct_names_and_all_interval_bounds(self):
  self.assertEqual(len({x['key'] for x in f.PUBLIC_STUDIES}),6)
  for s in f.PUBLIC_STUDIES:
   self.assertGreater(s['median_km']-s['minus_km'],0)
   self.assertGreater(s['plus_km'],0)
 def test_2026_shifted_paper_radius_interval(self):
  s=next(x for x in f.PUBLIC_STUDIES if x['key']=='Huang2026_shifted_dipole')
  self.assertAlmostEqual(s['median_km']-s['minus_km'],12.21,places=10)
  self.assertAlmostEqual(s['median_km']+s['plus_km'],14.75,places=10)
 def test_cannot_treat_outside_marginal_interval_as_exclusion(self):
  s=next(x for x in f.PUBLIC_STUDIES if x['key']=='Huang2026_shifted_dipole')
  self.assertIn('not_exclusion',f.diagnostic_flag(10.7,s)['label'])
 def test_inside_marginal_is_not_eos_likelihood(self):
  s=next(x for x in f.PUBLIC_STUDIES if x['key']=='Huang2026_shifted_dipole')
  self.assertIn('not_evidence',f.diagnostic_flag(13.0,s)['label'])
 def test_double_count_risk_same_2024_2026_photons(self):
  a={x['key']:x for x in f.PUBLIC_STUDIES}
  self.assertEqual(a['Salmi2024']['underlying_data'],a['Huang2026_shifted_dipole']['underlying_data'])
 def test_source_zip_hash_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bad.zip';p.write_bytes(b'fake')
   with self.assertRaisesRegex(ValueError,'F44_SOURCE_SHA_MISMATCH'):f.read_rns(p)
if __name__=='__main__':unittest.main(verbosity=2)
