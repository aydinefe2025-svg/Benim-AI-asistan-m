"""F58 mathematical tests. Synthetic likelihoods are not new NICER data."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import f58_common_tail_partial_identification as a


def fixture():
    w=.6
    q=.4
    e={key:{'conditional_on_verified_mass_window_L_over_Z':score,
            'likelihood_full_radio_prior_window_contribution':score*w,
            'mass_lo_msun':1.89,'mass_hi_msun':2.10,'mass_prior_coverage':w}
       for key,score in zip(a.EXPECTED_EOS,[.1,2.,1.9,.2,.3,.4,.5])}
    s={'common_24_direct_root_observational_integrals':e}
    return {'schema':'F51_pinned_F46_F48_F38_mass_support_expansion_v1',
            'status':'F51_NUMERICAL_MASS_SUPPORT_EXPANDED_NOT_NUCLEAR_EOS_BAYES',
            'direct_C_RNS_models_on_common_support':168,
            'common_verified_mass_window_msun':[1.89,2.10],
            'seven_source_nuclear_EOS_Bayes':'NOT_RUN',
            'native_photon_XPSI_joint_refit':'NOT_RUN',
            'common_radio_prior_mass_fraction_now':w,
            'remaining_prior_mass_fraction_uncomputed_for_all_seven':q,
            'surfaces':{f'surface_{i}':copy.deepcopy(s) for i in range(6)}}

class PartialIdentificationTests(unittest.TestCase):
    def test_exact_reversal_threshold_from_normalization(self):
        v=a.analyze(fixture())
        s=next(iter(v['surfaces'].values()))
        self.assertAlmostEqual(s['min_competitor_extra_unknown_tail_mean_to_reverse_if_leader_tail_is_zero'],.15,12)
        self.assertEqual(s['in_window_top_model'],'ENG')
        self.assertFalse(v['hard_science_boundary']['ranking_identifiable_with_nonnegative_but_unbounded_tail'])

    def test_unknown_tail_bounded_model_sets(self):
        s=next(iter(a.analyze(fixture())['surfaces'].values()))
        d={x['hypothetical_upper_bound_B_for_every_model_tail_mean_L_over_Z']:x for x in s['possible_winner_scenarios']}
        self.assertEqual(d[.05]['possible_winners_under_independent_nonnegative_tail_mean'],['ENG'])
        self.assertEqual(d[.2]['possible_winners_under_independent_nonnegative_tail_mean'],['ENG','MPA1'])
        self.assertEqual(d[.05]['unique_winner_guaranteed_by_this_bound'],'ENG')
        self.assertIsNone(d[.2]['unique_winner_guaranteed_by_this_bound'])

    def test_negative_likelihood_rejected(self):
        d=fixture();x=d['surfaces']['surface_0']['common_24_direct_root_observational_integrals']['ENG'];x['conditional_on_verified_mass_window_L_over_Z']=-2;x['likelihood_full_radio_prior_window_contribution']=-1.2
        with self.assertRaisesRegex(ValueError,'NEGATIVE_OR_NONFINITE'):
            a.analyze(d)

    def test_mismatched_radio_prior_weight_rejected(self):
        d=fixture();d['remaining_prior_mass_fraction_uncomputed_for_all_seven']=.399
        with self.assertRaisesRegex(ValueError,'NOT_COMPLEMENTARY'):
            a.analyze(d)

    def test_one_incorrect_source_likelihood_contribution_rejected(self):
        d=fixture();d['surfaces']['surface_1']['common_24_direct_root_observational_integrals']['ENG']['likelihood_full_radio_prior_window_contribution']=1
        with self.assertRaisesRegex(ValueError,'DOES_NOT_MATCH_INDEPENDENT_WEIGHTING'):
            a.analyze(d)

    def test_no_arbitrary_eos_specific_mass_window(self):
        d=fixture();d['surfaces']['surface_2']['common_24_direct_root_observational_integrals']['WFF1']['mass_hi_msun']=2.12
        with self.assertRaisesRegex(ValueError,'MASS_WINDOW_MISMATCH'):
            a.analyze(d)

    def test_missing_model_or_surface_rejected(self):
        d=fixture();d['surfaces']['surface_3']['common_24_direct_root_observational_integrals'].pop('WFF1')
        with self.assertRaisesRegex(ValueError,'EOS_LIST'):
            a.analyze(d)
        d=fixture();d['surfaces'].pop('surface_3')
        with self.assertRaisesRegex(ValueError,'BANDWIDTH'):
            a.analyze(d)

    def test_model_is_not_original_nuclear_eos_posterior(self):
        d=fixture();d['seven_source_nuclear_EOS_Bayes']='PASS'
        with self.assertRaisesRegex(ValueError,'NUCLEAR_EOS_BAYES'):
            a.analyze(d)

    def test_source_lock_sha256_declared(self):
        self.assertEqual(len(a.PINNED_F51_JSON_SHA256),64)
        self.assertEqual(a.PINNED_F51_JSON_SHA256,'3c3584905190012ee61f4b7fee343e3d1c9e28300f9d681e8bf34dd157b5d67d')

if __name__=='__main__':unittest.main()