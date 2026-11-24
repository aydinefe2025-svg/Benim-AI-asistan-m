"""Single-RC EIS baseline: independent synthetic fixtures, real publisher replay in CI."""
import math
import unittest

from research.battery_curve_audit import graz_eis_rc_frequency_holdout as rc

def fake_spectrum(rs=0.004,rp=0.009,tau=0.018,n=101):
    hz=[10**(-2+7*k/(n-1)) for k in range(n)]
    return [(f,abs(z),math.degrees(math.atan2(z.imag,z.real)))
            for f in hz for z in [complex(rs,0)+rp/(1+1j*2*math.pi*f*tau)]]

class SingleRCHoldoutTests(unittest.TestCase):
    def test_exact_synthetic_frequency_generalization(self):
        r=rc.cross_validate(fake_spectrum())
        self.assertEqual(r['observed_frequency_count'],101)
        self.assertEqual(r['fold_test_counts'],[50,51])
        self.assertLess(r['heldout_relative_complex_rmse_pct'],1.)
        self.assertTrue(all(f['Rs_ohm']>=0 and f['Rp_ohm']>=0 and f['tau_s']>0 for f in r['folds']))
    def test_inductive_synthetic_not_silently_fit_by_passive_rc(self):
        source=fake_spectrum()
        inductive=[(f,abs(z),math.degrees(math.atan2(z.imag,z.real))) for f,mag,ang in source
                   for z in [mag*complex(math.cos(math.radians(ang)),math.sin(math.radians(ang)))+1j*2*math.pi*f*1e-5]]
        r=rc.cross_validate(inductive)
        self.assertGreater(r['heldout_relative_complex_rmse_pct'],10.0)
        self.assertGreater(r['positive_phase_frequency_count'],0)
        self.assertFalse(r['independent_calibration_verified'])
    def test_two_parity_folds_no_overlap(self):
        r=rc.cross_validate(fake_spectrum())
        self.assertEqual(r['fold_train_counts'],[51,50])
        self.assertEqual(r['fold_test_counts'],[50,51])
    def test_reject_duplicate_or_unsorted_frequency(self):
        s=fake_spectrum();s[4]=s[3]
        with self.assertRaises(ValueError):rc.cross_validate(s)
    def test_reject_nonfinite_magnitude(self):
        s=fake_spectrum();s[5]=(s[5][0],float('nan'),0)
        with self.assertRaises(ValueError):rc.cross_validate(s)
    def test_reject_zero_frequency(self):
        s=fake_spectrum();s[0]=(0.,s[0][1],s[0][2])
        with self.assertRaises(ValueError):rc.cross_validate(s)
    def test_reject_negative_magnitude(self):
        s=fake_spectrum();s[0]=(s[0][0],-1.,s[0][2])
        with self.assertRaises(ValueError):rc.cross_validate(s)
    def test_reject_inadequate_frequency_samples(self):
        with self.assertRaises(ValueError):rc.cross_validate(fake_spectrum(n=3))
    def test_known_source_five_stages_requires_same_grids(self):
        baseline=fake_spectrum()
        stages={n:list(baseline) for n in rc.LEVELS}
        stages[rc.LEVELS[3]][2]=(99.,baseline[2][1],baseline[2][2])
        with self.assertRaises(ValueError):
            rc.compare_source_stages(stages,'EIS_C02.xlsx')
    def test_no_laboratory_certificate_from_fit(self):
        r=rc.cross_validate(fake_spectrum())
        self.assertFalse(r['absolute_parameter_identification_verified'])
        self.assertFalse(r['independent_calibration_verified'])
        self.assertFalse(r['production_release_allowed'])

if __name__=='__main__':unittest.main()
