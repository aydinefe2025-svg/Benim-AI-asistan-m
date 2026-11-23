"""Fail-closed positive Debye relaxation controls against mathematical ground truth."""
import importlib.util
import math
import unittest
from research.battery_curve_audit import graz_eis_positive_relaxation as drt
NUMERICS = importlib.util.find_spec('numpy') and importlib.util.find_spec('scipy')

def generate(n=101,nonpassive=False):
    arr=[]
    for i in range(n):
        f=10**(-2+7*i/(n-1))
        z=0.009+1j*2*math.pi*f*3e-5+0.008/(1+1j*2*math.pi*f*0.02)+0.006/(1+1j*2*math.pi*f*0.3)+0.003/(1+1j*2*math.pi*f*4)
        if nonpassive:z=-z
        arr.append((f,abs(z),math.degrees(math.atan2(z.imag,z.real))))
    return arr

class PositiveRelaxation(unittest.TestCase):
    def test_source_identity_monotonic(self):
        x=drt.validate_source(generate())
        self.assertEqual(len(x),101)
    def test_invalid_source_fails_without_numeric_package(self):
        v=generate();v[3]=v[2]
        with self.assertRaises(ValueError):drt.validate_source(v)
    def test_zero_source_amplitude_fails(self):
        v=generate();v[3]=(v[3][0],0.,v[3][2])
        with self.assertRaises(ValueError):drt.validate_source(v)
    @unittest.skipUnless(NUMERICS,'full scipy model tested in dedicated original-source workflow')
    def test_approximate_three_relaxation_arcs_out_of_sample(self):
        r=drt.cross_validate(generate(),weighting='absolute')
        self.assertEqual(r['total_frequency_predictions'],101)
        self.assertLess(r['heldout_complex_rmse_pct'],5)
        self.assertTrue(r['all_nonnegative_relaxation_coefficients'])
    @unittest.skipUnless(NUMERICS,'full scipy model tested in dedicated original-source workflow')
    def test_holdout_bands_are_excluded(self):
        r=drt.block_holdout(generate())
        self.assertTrue(r['no_train_test_frequency_overlap'])
        self.assertEqual(r['train_count']+r['test_count'],101)
    @unittest.skipUnless(NUMERICS,'full scipy model tested in dedicated original-source workflow')
    def test_relative_weighting_returns_nonnegative_coefficients(self):
        r=drt.cross_validate(generate(),weighting='relative')
        self.assertTrue(r['all_nonnegative_relaxation_coefficients'])
        self.assertLess(r['heldout_complex_rmse_pct'],5)
    @unittest.skipUnless(NUMERICS,'full scipy model tested in dedicated original-source workflow')
    def test_nonpassive_fixture_not_false_certificate(self):
        r=drt.cross_validate(generate(nonpassive=True))
        self.assertFalse(r['kramers_kronig_consistency_proven'])
        self.assertFalse(r['independent_instrument_calibration_verified'])
    @unittest.skipUnless(NUMERICS,'full scipy model tested in dedicated original-source workflow')
    def test_reproducibility_fixed_relaxation_grid(self):
        a=drt.cross_validate(generate())
        b=drt.cross_validate(generate())
        self.assertEqual(a['heldout_complex_rmse_pct'],b['heldout_complex_rmse_pct'])
if __name__=='__main__':unittest.main()