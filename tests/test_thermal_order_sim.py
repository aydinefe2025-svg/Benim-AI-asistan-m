import copy
import json
import math
from pathlib import Path
import unittest
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'/'battery_curve_audit'))
from thermal_order_sim import (read_pinned,validate,rank,make_design_matrix,fixed_order,balanced_order,
                               thermal_residual,model_source,SOURCE_SHA)
SRC=ROOT/'research'/'battery_curve_audit'/'fixtures'/'k01_k04_k05_nine_source_27_pairs_pinned.json'
class TestThermalOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=read_pinned(SRC)
        cls.output=model_source(cls.source,repetitions=1000)
    def test_all_sources_distinct(self): self.assertEqual(len(validate(self.source)),9)
    def test_temperature_count(self):self.assertEqual(sum(len(x) for x in validate(self.source).values()),27)
    def test_four_discordant(self):self.assertEqual(sum(x['mixed_or_zero_channel_sign'] for x in self.source['source_results']),4)
    def test_all_nine_t10_excess(self):self.assertEqual(self.output['observed_source_derived']['t10_greater_than_mean_t23_t45_source_count'],9)
    def test_mean_t10_greater(self):self.assertGreater(self.output['observed_source_derived']['mean_absolute_channel_gap_pp_by_temp']['10'],1.0)
    def test_bootstrap_reproducible(self):self.assertEqual(model_source(self.source,repetitions=1000,seed=21),model_source(self.source,repetitions=1000,seed=21))
    def test_fixed_order_confounded(self):self.assertEqual(rank(make_design_matrix(fixed_order())),11)
    def test_balanced_rank_full(self):self.assertEqual(rank(make_design_matrix(balanced_order())),13)
    def test_each_temperature_each_period_balanced(self):
        for i in range(3): self.assertEqual(sorted(x[i] for x in balanced_order()),[10]*3+[23]*3+[45]*3)
    def test_thermal_zero_time(self):self.assertEqual(thermal_residual(35,0,30),35)
    def test_thermal_lower_with_higher_hold(self):self.assertLess(thermal_residual(35,120,30),thermal_residual(35,60,30))
    def test_thermal_higher_tau_slower(self):self.assertGreater(thermal_residual(35,120,60),thermal_residual(35,120,30))
    def test_thermal_invalid_tau(self):
        with self.assertRaises(ValueError): thermal_residual(35,10,0)
    def test_corrupt_source_rejected(self):
        d=copy.deepcopy(self.source);d['source_results'][0]['discharge_change_percent']=float('nan')
        with self.assertRaises(ValueError): validate(d)
    def test_bad_source_count(self):
        d=copy.deepcopy(self.source);d['source_results'].pop()
        with self.assertRaises(ValueError):validate(d)
    def test_duplicate_source_temperature(self):
        d=copy.deepcopy(self.source);d['source_results'][1]=copy.deepcopy(d['source_results'][0])
        with self.assertRaises(ValueError):validate(d)
    def test_fake_physical_claim_rejected(self):
        self.assertFalse(self.output['actual_physical_calibration'])
        self.assertFalse(self.output['product_field_release_allowed'])
    def test_source_bad_hash_rejected(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            p=Path(d)/'fake.json';p.write_text(json.dumps(self.source).replace('27','28',1))
            with self.assertRaises(ValueError):read_pinned(p)
if __name__=='__main__':unittest.main()