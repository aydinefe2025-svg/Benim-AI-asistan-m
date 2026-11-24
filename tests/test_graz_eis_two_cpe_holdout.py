"""Two-arc CPE EIS model, source-independent falsification/holdout contracts."""
import math
import unittest
import importlib.util

from research.battery_curve_audit import graz_eis_two_cpe_holdout as cpe


def synthetic(model='two', n=51):
    frequencies=[10**(-2+6*i/(n-1)) for i in range(n)]
    z=[]
    for hz in frequencies:
        if model=='two':
            v=(0.006+0.0001j*2*math.pi*hz +
               0.014/(1+(1j*2*math.pi*hz*0.04)**0.80) +
               0.008/(1+(1j*2*math.pi*hz*4)**0.62))
        elif model=='one':
            v=0.008+1j*0.00005*2*math.pi*hz+0.018/(1+(1j*2*math.pi*hz*0.03)**0.72)
        else:raise ValueError
        z.append((hz,abs(v),math.degrees(math.atan2(v.imag,v.real))))
    return z

SCIENCE_DEPS = (importlib.util.find_spec("numpy") is not None and
                importlib.util.find_spec("scipy") is not None)

class TwoCPEHoldout(unittest.TestCase):
    def test_publishers_exact_50_point_spectrum_contract(self):
        p=cpe.validate_spectrum(synthetic(n=101))
        self.assertEqual(len(p),101)
        self.assertTrue(all(phase[0]>0 for phase in p))
    @unittest.skipUnless(SCIENCE_DEPS, "full SciPy/NumPy fit exercised in dedicated original-source CI")
    def test_fitted_two_arc_recovers_synthetic_heldout(self):
        r=cpe.cross_validate(synthetic(),model='two_cpe')
        self.assertEqual(sum(x['test_count'] for x in r['folds']),51)
        self.assertEqual(r['folds'][0]['test_count'],25)
        self.assertLess(r['heldout_relative_complex_rmse_pct'],2)
        self.assertTrue(all(f['constraints_passed'] for f in r['folds']))
    @unittest.skipUnless(SCIENCE_DEPS, "full SciPy/NumPy fit exercised in dedicated original-source CI")
    def test_simple_one_arc_cpe_suffices_for_one_process(self):
        r=cpe.cross_validate(synthetic('one'),model='one_cpe')
        self.assertLess(r['heldout_relative_complex_rmse_pct'],2)
    @unittest.skipUnless(SCIENCE_DEPS, "full SciPy/NumPy fit exercised in dedicated original-source CI")
    def test_no_heldout_frequency_used_in_its_own_training_fold(self):
        r=cpe.cross_validate(synthetic(),model='two_cpe')
        self.assertEqual([x['train_count'] for x in r['folds']],[26,25])
        self.assertEqual([x['test_count'] for x in r['folds']],[25,26])
        self.assertEqual(r['unique_heldout_frequency_count'],51)
        self.assertTrue(r['disjoint_train_test_indices_verified'])
    def test_duplicate_original_frequency_fails_closed(self):
        p=synthetic();p[10]=p[9]
        with self.assertRaises(ValueError):cpe.cross_validate(p,model='two_cpe')
    def test_nonfinite_original_phase_fails_closed(self):
        p=synthetic();p[4]=(p[4][0],p[4][1],float('inf'))
        with self.assertRaises(ValueError):cpe.cross_validate(p,model='two_cpe')
    def test_zero_original_magnitude_fails_closed(self):
        p=synthetic();p[3]=(p[3][0],0.,p[3][2])
        with self.assertRaises(ValueError):cpe.cross_validate(p,model='two_cpe')
    def test_unsupported_model_rejected(self):
        with self.assertRaises(ValueError):cpe.cross_validate(synthetic(),model='flexible_fake')
    @unittest.skipUnless(SCIENCE_DEPS, "full SciPy/NumPy fit exercised in dedicated original-source CI")
    def test_contiguous_block_is_unseen_when_fitted(self):
        r=cpe.contiguous_block_holdout(synthetic(n=101),model='two_cpe')
        self.assertEqual(r['train_count']+r['test_count'],101)
        self.assertTrue(r['disjoint_train_test_indices_verified'])
        self.assertGreaterEqual(r['test_count'],25)
    @unittest.skipUnless(SCIENCE_DEPS, "full SciPy/NumPy fit exercised in dedicated original-source CI")
    def test_simulation_never_certifies_physical_damage(self):
        r=cpe.cross_validate(synthetic(),model='two_cpe')
        self.assertFalse(r['mechanistic_identifiability_proven'])
        self.assertFalse(r['production_release_allowed'])
        self.assertFalse(r['capacity_loss_Ah_measured'])

if __name__=='__main__':unittest.main()