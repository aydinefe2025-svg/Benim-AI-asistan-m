"""Series-inductance EIS red-team: independently hold out true frequencies."""
import math
import unittest
from research.battery_curve_audit import graz_eis_rc_frequency_holdout as rc
from research.battery_curve_audit import graz_eis_rlc_frequency_holdout as rlc

def sample(inductance_h=1e-5):
    rs=0.004;rp=0.009;tau=0.018
    data=[]
    for j in range(101):
        f=10**(-2+7*j/100)
        z=complex(rs,0)+rp/(1+1j*2*math.pi*f*tau)+1j*2*math.pi*f*inductance_h
        data.append((f,abs(z),math.degrees(math.atan2(z.imag,z.real))))
    return data

class RCLFrequencyHoldout(unittest.TestCase):
    def test_inductive_fixture_beats_simple_rc_blind(self):
        original=rc.cross_validate(sample())
        robust=rlc.cross_validate_rlc(sample())
        self.assertGreater(original['heldout_relative_complex_rmse_pct'],10)
        self.assertLess(robust['heldout_relative_complex_rmse_pct'],1.5)
        self.assertEqual(robust['fold_test_counts'],[50,51])
        self.assertEqual(robust['observed_frequency_count'],101)
    def test_absent_inductance_does_not_need_negative_inductor(self):
        robust=rlc.cross_validate_rlc(sample(inductance_h=0))
        self.assertLess(robust['heldout_relative_complex_rmse_pct'],1.5)
        self.assertTrue(all(x['series_inductance_h']>=0 for x in robust['folds']))
    def test_fitted_component_nonnegative(self):
        robust=rlc.cross_validate_rlc(sample())
        for x in robust['folds']:
            self.assertGreaterEqual(x['Rs_ohm'],0)
            self.assertGreaterEqual(x['Rp_ohm'],0)
            self.assertGreaterEqual(x['series_inductance_h'],0)
            self.assertGreater(x['tau_s'],0)
    def test_source_channel_not_lab_calibration(self):
        robust=rlc.cross_validate_rlc(sample())
        self.assertFalse(robust['series_inductance_independently_calibrated'])
        self.assertFalse(robust['production_release_allowed'])
    def test_reject_invalid_original_spectrum(self):
        raw=sample()
        raw[9]=(raw[8][0],raw[9][1],raw[9][2])
        with self.assertRaises(ValueError):rlc.cross_validate_rlc(raw)
if __name__=='__main__':unittest.main()
