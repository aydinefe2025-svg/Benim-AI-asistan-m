import unittest
from research.battery_curve_audit import graz_third_reference_stress as stress

class StressTests(unittest.TestCase):
    def test_one_seed_replay_and_truthful_negative(self):
        a=stress.run(seeds=1,seed_start=99)
        b=stress.run(seeds=1,seed_start=99)
        self.assertEqual(a,b)
        self.assertEqual(len(a['scenarios']),14)
        self.assertEqual(a['total_synthetic_samples'],14*5*240)
        results={x['scenario']:x for x in a['scenarios']}
        self.assertEqual(results['two_clock_roots_correlated_compromise']['accepted'],0)
        self.assertGreater(results['all_three_reference_domains_compromised']['wrong_time_accepted'],0)
        self.assertFalse(a['physical_production_release_allowed'])
    def test_bad_seed_count_rejected(self):
        for x in (0,201,False,1.2):
            with self.subTest(x=x),self.assertRaises(ValueError):stress.run(seeds=x)

if __name__=='__main__':unittest.main()