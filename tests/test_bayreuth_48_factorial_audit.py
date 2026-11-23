"""stdlib-only regression and fail-closed tests for publisher 48-cell audit."""
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
MODULE = HERE.parent / "research" / "battery_curve_audit" / "bayreuth_48_factorial_audit.py"
if not MODULE.exists():
    MODULE = HERE / "bayreuth_48_factorial_audit.py"
spec=importlib.util.spec_from_file_location("bayreuth_factorial",MODULE)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
CSV=MODULE.with_name("bayreuth_48_publisher_cf.csv")

class TestSourceData(unittest.TestCase):
    def setUp(self):
        self.source=audit.load_source_csv(CSV)
    def test_pin(self): self.assertEqual(len(self.source),48)
    def test_unique_cells(self):self.assertEqual(len(set(r['cell_id'] for r in self.source)),48)
    def test_balanced(self):self.assertEqual(len({(r['temp_c'],r['c_rate']) for r in self.source}),24)
    def test_checksum_failure(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"alter.csv";p.write_bytes(CSV.read_bytes()+b"\n")
            with self.assertRaisesRegex(ValueError,"SHA256"):audit.load_source_csv(p)
    def mutate_and_fail(self,transform):
        s=CSV.read_text();modified=transform(s)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"alter.csv";p.write_text(modified)
            with self.assertRaises(ValueError):audit.load_source_csv(p,enforce_sha=False)
    def test_duplicates_rejected(self):
        self.mutate_and_fail(lambda s:s.replace('F0002,','F0001,'))
    def test_nonfinite_rejected(self):
        self.mutate_and_fail(lambda s:s.replace(s.splitlines()[1].split(',')[-1],"nan",1))
    def test_missing_row_rejected(self):
        self.mutate_and_fail(lambda s:'\n'.join(s.splitlines()[:-1])+'\n')
    def test_unexpected_temperature_rejected(self):
        self.mutate_and_fail(lambda s:s.replace('F0001,25,','F0001,24,'))
    def test_unexpected_rate_rejected(self):
        self.mutate_and_fail(lambda s:s.replace('F0001,25,1.5,','F0001,25,1.4,'))
    def test_anova_closure_and_f(self):
        r=audit.factorial_audit(self.source)
        self.assertAlmostEqual(r['ss_total'],310.460691731549,places=9)
        self.assertAlmostEqual(r['anova_fixed_effects_descriptive']['interaction']['F_exploratory'],15.062523122940407,places=9)
    def test_all_rates_positive(self):
        r=audit.factorial_audit(self.source)
        self.assertTrue(r['cf_difference_0C_minus_25C_all_rates_positive'])
        self.assertAlmostEqual(r['temperature_mean_cf_pct']['0']-r['temperature_mean_cf_pct']['25'],5.5078393821989565,places=9)
    def test_no_causal_claims(self):
        r=audit.factorial_audit(self.source)
        self.assertTrue(all(v is False for v in r['claims'].values()))

if __name__=='__main__':unittest.main()