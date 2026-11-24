import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import agv_variable_load_model as model
class TestModel(unittest.TestCase):
    def test_quantile_small_sample(self):
        self.assertEqual(model.calibration_radius([1,2,3,4,5,6,7,8,9], .2),8)
    def test_calibration_insufficient(self):
        with self.assertRaises(ValueError):model.calibration_radius([1],.1)
    def test_interval_nonnegative_and_coverage(self):
        x=model.interval_stats([0,4,7],[1,3,3],2)
        self.assertEqual(x['covered'],2); self.assertEqual(x['lower_Ah'],[0,1,1]);self.assertEqual(x['upper_Ah'],[3,5,5])
    def test_linear_fixed_rate(self):
        rows=[{'pack':p,'operating_s':3600,'previous_operating_s':3600,'days_between_start_dates':0,'delta_Ah':i+1} for i,p in enumerate(model.PACKS)]
        c=model.fit(rows,'constant',0)
        np.testing.assert_allclose(model.predict(rows,'constant',c),np.arange(1,11))
    def test_split_purge(self):
        rows=[]
        for i in range(1,11):
            rows.append(dict(date=f'2021-01-{i:02d}',previous_date=f'2021-01-{max(1,i-1):02d}',operating_s=600,days_between_start_dates=1))
        tr,v,te,a,b=model.split(rows)
        self.assertTrue(all(r['previous_date']>=a for r in v));self.assertTrue(all(r['previous_date']>=b for r in te));self.assertEqual(len(tr)+len(v)+len(te),8)
    def test_reject_unverified_receipt(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'receipt.json'; p.write_text('{}')
            with self.assertRaisesRegex(ValueError,'receipt SHA-256 mismatch'):
                model.load_source(p)
    @unittest.skipUnless(Path('AGV_ADJACENT_CURRENT_RECEIPT.json').is_file(), 'requires real replay receipt')
    def test_original_json_reproduces_heldout_result(self):
        # The source workflow must produce this receipt from publisher bytes first.
        r=model.run(Path('AGV_ADJACENT_CURRENT_RECEIPT.json'))
        self.assertEqual((r['train_n'],r['validation_n'],r['test_n']),(472,166,147))
        self.assertEqual(r['selected']['kind'],'constant')
        self.assertAlmostEqual(r['selected_test']['mae_Ah'],1.1690713218394249,places=10)
        self.assertEqual(r['empirical_90pct_target_interval']['covered'],140)

if __name__=='__main__':unittest.main()