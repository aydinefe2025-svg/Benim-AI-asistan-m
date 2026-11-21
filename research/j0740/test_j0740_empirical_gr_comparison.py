import copy
import json
from pathlib import Path
import unittest
import numpy as np

from j0740_empirical_gr_comparison import audit,compare_curve,verify_bytes,EOS,EXPECTED_MASS,EXPECTED_SPIN


def fake_row():
    return {"status":"MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED",
            "rns_rotating_at_target":{"mass_msun":EXPECTED_MASS,"radius_eq_km":12.53,"spin_hz_reported":346.5},
            "rns_static_at_same_gravitational_mass":{"mass_msun":EXPECTED_MASS,"radius_eq_km":12.40,"spin_hz_reported":0}}

class RotationFitVsGRTests(unittest.TestCase):
    def setUp(self):
        self.knots=[[1.8,12.6],[1.9,12.55],[2.0,12.5],[2.073,12.45],[2.13,12.4],[2.2,12.3]]

    def test_empirical_radius_and_decomposition(self):
        row=compare_curve(self.knots,fake_row(),EXPECTED_MASS,EXPECTED_SPIN)
        total=row['f30_minus_rns_rotating_radius_km']
        reconstructed=(row['difference_of_rotation_corrections_at_same_MG_km']+
                       row['f30_static_curve_minus_rns_static_km'])
        self.assertAlmostEqual(total,reconstructed,places=11)
        self.assertGreater(row['f30_empirical_reference_mass_shift_msun'],0)

    def test_not_fixed_gravitational_mass_rejects(self):
        row=fake_row();row['rns_rotating_at_target']['mass_msun']=2.08
        with self.assertRaisesRegex(ValueError,'fixed'):
            compare_curve(self.knots,row,EXPECTED_MASS,EXPECTED_SPIN)

    def test_wrong_spin_rejects(self):
        row=fake_row();row['rns_rotating_at_target']['spin_hz_reported']=370
        with self.assertRaisesRegex(ValueError,'frequency'):
            compare_curve(self.knots,row,EXPECTED_MASS,EXPECTED_SPIN)

    def test_wrong_static_control_rejects(self):
        row=fake_row();row['rns_static_at_same_gravitational_mass']['spin_hz_reported']=25
        with self.assertRaisesRegex(ValueError,'nonrotating'):
            compare_curve(self.knots,row,EXPECTED_MASS,EXPECTED_SPIN)

    def test_knot_nonmonotonicity_rejects(self):
        bad=copy.deepcopy(self.knots);bad[3][0]=bad[2][0]
        with self.assertRaisesRegex(ValueError,'increasing'):
            compare_curve(bad,fake_row(),EXPECTED_MASS,EXPECTED_SPIN)

    def test_knots_extrapolation_rejects(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            compare_curve(self.knots,fake_row(),2.3,EXPECTED_SPIN)

    def test_unvalidated_gr_rejects(self):
        row=fake_row();row['status']='NOT_COMPUTED'
        with self.assertRaisesRegex(ValueError,'Unvalidated'):
            compare_curve(self.knots,row,EXPECTED_MASS,EXPECTED_SPIN)

    def test_unmatched_eos_set_rejects(self):
        gr={"status":"ALL_SEVEN_VALIDATED","validated_eos_count":7,
            "target_gravitational_mass_msun":EXPECTED_MASS,"spin_hz":EXPECTED_SPIN,
            "eos":{k:fake_row() for k in EOS}}
        with self.assertRaisesRegex(ValueError,'identities'):
            audit({k:self.knots for k in EOS[:-1]},gr)

    def test_source_bytes_must_be_pinned(self):
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
            verify_bytes(Path(__file__), '0'*64)

if __name__=="__main__":unittest.main()
