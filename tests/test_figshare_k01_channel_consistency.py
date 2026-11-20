import copy
import unittest
from research.battery_curve_audit.figshare_k01_channel_consistency import review_source_profiles

def make_input():
    cells=[]
    ids={4:47639005,5:47627092,6:47627089}
    for no in (4,5,6):
        profiles=[]
        for temp in (10,23,45):
            et_qch,et_qdch=5.,5.
            if temp==10 and no in (4,5):
                at_qch,at_qdch=4.9,5.001
            else:
                at_qch,at_qdch=4.95,4.97
            profiles.append({"temperature_C":temp,
                "et_capacity_Ah":5.0,
                "at_capacity_Ah":round((at_qch+at_qdch)/2,6),
                "et_charge_capacity_Ah":et_qch,
                "et_discharge_capacity_Ah":et_qdch,
                "at_charge_capacity_Ah":at_qch,
                "at_discharge_capacity_Ah":at_qdch,
                "et_to_at_change_percent":round(100*((at_qch+at_qdch)/10-1),4),
                "source_sidecar_identity_matched":True,
                "original_step21_and_step22_valid_both_phases":True,
                "measurement_source_temperature_matched":True,
                "physical_identity_independently_authenticated":False,
                "storage_only_aging_attribution_proved":False})
        cells.append({"publisher_file_id":ids[no],
                      "source_profiles":profiles,"original_crc_verified":True,
                      "publisher_md5_verified":True})
    return {"schema":"cano.battery.figshare279.original-k01-3cell-3temp-et-at-capacity.v1",
      "source_doi":"10.6084/m9.figshare.25975315",
      "source_archives":cells,"original_archives_verified":3,
      "source_capacity_pair_count":9,
      "external_physical_cell_custody_authenticated":False,
      "field_FPR_FNR_established":False,
      "storage_only_aging_attribution_proven":False,
      "commercial_release_allowed":False}

class ChannelGateTests(unittest.TestCase):
    def test_two_mixed_sign_pairs_not_nine_concordant_losses(self):
        out=review_source_profiles(make_input())
        self.assertEqual(out['mean_negative_pairs'],9)
        self.assertEqual(out['both_charge_and_discharge_negative_pairs'],7)
        self.assertEqual(out['mixed_sign_pairs'],2)
        d={(r['source_archive_id'],r['temperature_C']):r for r in out['comparisons']}
        for cell in (4,5):
            self.assertEqual(d[({4:47639005,5:47627092}[cell],10)]['decision'],'MIXED_SIGN_MEAN_LOSS_NOT_BOTH_CHANNEL_LOSS')
        self.assertFalse(out['field_FPR_FNR_established'])
        self.assertFalse(out['production_release_allowed'])
    def test_forced_source_claim_rejected(self):
        x=make_input();x['field_FPR_FNR_established']=True
        with self.assertRaisesRegex(ValueError,'unsupported'):
            review_source_profiles(x)
    def test_inconsistent_mean_rejected(self):
        x=make_input();x['source_archives'][0]['source_profiles'][0]['et_capacity_Ah']=3.1
        with self.assertRaisesRegex(ValueError,'mean'):
            review_source_profiles(x)
    def test_nan_and_boolean_capacity_rejected(self):
        for fake in ('NaN',True,0,-1):
            with self.subTest(fake=fake):
                x=make_input();x['source_archives'][0]['source_profiles'][0]['et_charge_capacity_Ah']=fake
                with self.assertRaises(ValueError):review_source_profiles(x)
    def test_duplicate_source_id_rejected(self):
        x=make_input();x['source_archives'][1]['publisher_file_id']=47639005
        with self.assertRaisesRegex(ValueError,'duplicate'):
            review_source_profiles(x)
    def test_missing_temperature_rejected(self):
        x=make_input();x['source_archives'][0]['source_profiles'][0]['temperature_C']=45
        with self.assertRaisesRegex(ValueError,'temperature'):
            review_source_profiles(x)
    def test_invalid_source_hash_flags_rejected(self):
        x=make_input();x['source_archives'][0]['publisher_md5_verified']=False
        with self.assertRaisesRegex(ValueError,'source'):
            review_source_profiles(x)
    def test_synthetic_zero_channel_delta_is_undecided(self):
        x=make_input();p=x['source_archives'][0]['source_profiles'][1]
        p.update(at_charge_capacity_Ah=5.,at_discharge_capacity_Ah=4.9,
                 at_capacity_Ah=4.95,et_to_at_change_percent=-1.)
        out=review_source_profiles(x)
        r=next(r for r in out['comparisons'] if r['source_archive_id']==47639005 and r['temperature_C']==23)
        self.assertEqual(r['decision'],'ZERO_DIRECTION_CHANNEL_REVIEW_REQUIRED')

if __name__=='__main__':unittest.main()