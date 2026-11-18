"""F58: mathematically exact partial identification of F51 seven-EOS scores.

No new observational likelihood or C/GR run is performed.
Only source-locked F51 common-window outputs are used. A hypothetical full
score for a model i is S_i = w * L_i(window) + (1-w) * T_i(tail), where
T_i is the unknown nonnegative radio-prior-conditional average likelihood
outside the existing same [1.89,2.10] M_sun window. This decomposition is
*not* a photon-level or physics-prior EOS Bayes factor and is *not*
well-defined for globally disjoint/invalid physical branches without a
specified EOS-dependent prior. The tested bounded-tail scenarios are
sensitivity assumptions, not empirical constraints on T_i.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

PINNED_F51_JSON_SHA256 = '3c3584905190012ee61f4b7fee343e3d1c9e28300f9d681e8bf34dd157b5d67d'
EXPECTED_EOS = ('APR4_EPP', 'ENG', 'MPA1', 'MS1', 'MS1B', 'WFF1', 'WFF2')
EXPECTED_MASS_WINDOW = (1.89, 2.10)
BOUNDS = (0.0, 0.05, 0.10, 0.20, 1.0)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(data: dict) -> tuple[float, float]:
    if data.get('schema') != 'F51_pinned_F46_F48_F38_mass_support_expansion_v1':
        raise ValueError('F58_SOURCE_IS_NOT_GENUINE_F51')
    if data.get('status') != 'F51_NUMERICAL_MASS_SUPPORT_EXPANDED_NOT_NUCLEAR_EOS_BAYES':
        raise ValueError('F58_F51_STATUS_DOES_NOT_PRESERVE_PHYSICS_CAVEAT')
    if data.get('direct_C_RNS_models_on_common_support') != 168:
        raise ValueError('F58_SOURCE_DOES_NOT_HAVE_168_REAL_C_STARS')
    if list(map(float,data['common_verified_mass_window_msun'])) != list(EXPECTED_MASS_WINDOW):
        raise ValueError('F58_COMMON_WINDOW_DIFFERS_FROM_SOURCE')
    if data.get('seven_source_nuclear_EOS_Bayes') != 'NOT_RUN':
        raise ValueError('F58_CANNOT_TREAT_SOURCE_AS_NUCLEAR_EOS_BAYES')
    if data.get('native_photon_XPSI_joint_refit') != 'NOT_RUN':
        raise ValueError('F58_SOURCE_LIKELIHOOD_CONFLICT')
    w = float(data['common_radio_prior_mass_fraction_now'])
    q = float(data['remaining_prior_mass_fraction_uncomputed_for_all_seven'])
    if not (0 < w < 1 and 0 < q < 1 and math.isclose(w+q,1,rel_tol=0,abs_tol=1e-12)):
        raise ValueError('F58_UNCOMPUTED_PRIOR_WEIGHT_NOT_COMPLEMENTARY')
    if len(data.get('surfaces', {})) != 6:
        raise ValueError('F58_MISSING_SOURCE_KDE_BANDWIDTH_SURFACES')
    return w, q


def one_surface(surface:dict,w:float,q:float, bounds=BOUNDS) -> dict:
    entries = surface['common_24_direct_root_observational_integrals']
    if set(entries) != set(EXPECTED_EOS):
        raise ValueError('F58_EOS_LIST_OR_COMMON_WINDOW_INCOMPLETE')
    score = {}
    for model, record in entries.items():
        if record.get('mass_lo_msun') != EXPECTED_MASS_WINDOW[0] or record.get('mass_hi_msun') != EXPECTED_MASS_WINDOW[1]:
            raise ValueError('F58_MODEL_SPECIFIC_MASS_WINDOW_MISMATCH')
        if record.get('mass_prior_coverage') is None or abs(float(record['mass_prior_coverage'])-w)>1e-11:
            raise ValueError('F58_MASS_PRIOR_COVERAGE_NOT_COMMON')
        s = float(record['conditional_on_verified_mass_window_L_over_Z'])
        c = float(record['likelihood_full_radio_prior_window_contribution'])
        if not (math.isfinite(s) and s>=0 and math.isfinite(c) and c>=0):
            raise ValueError('F58_NEGATIVE_OR_NONFINITE_SOURCE_LIKELIHOOD')
        if not math.isclose(w*s,c,rel_tol=1e-10,abs_tol=1e-10):
            raise ValueError('F58_F51_CONTRIBUTION_DOES_NOT_MATCH_INDEPENDENT_WEIGHTING')
        score[model]={'in_window_conditional_L_over_Z':s,'in_window_full_prior_contribution':c}
    order=sorted(score,key=lambda key:(-score[key]['in_window_conditional_L_over_Z'],key))
    leader, runner = order[:2]
    gap=score[leader]['in_window_full_prior_contribution']-score[runner]['in_window_full_prior_contribution']
    if gap<0:raise ValueError('F58_CONTRADICTORY_IN_WINDOW_RANKING')
    reversal_threshold=gap/q
    scenarios=[]
    for b in bounds:
        if not math.isfinite(b) or b<0:raise ValueError('F58_TAIL_CAP_INVALID')
        intervals={m:{'minimum_full_score':score[m]['in_window_full_prior_contribution'],
                      'maximum_full_score_if_T_le_B':score[m]['in_window_full_prior_contribution']+q*b}
                   for m in EXPECTED_EOS}
        highest_guaranteed_floor=max(v['minimum_full_score'] for v in intervals.values())
        possible=sorted(m for m,v in intervals.items()
                        if v['maximum_full_score_if_T_le_B'] >= highest_guaranteed_floor - 1e-12)
        guaranteed=[m for m,v in intervals.items()
                    if all(v['minimum_full_score'] > v2['maximum_full_score_if_T_le_B']+1e-12
                           for m2,v2 in intervals.items() if m2!=m)]
        scenarios.append({'hypothetical_upper_bound_B_for_every_model_tail_mean_L_over_Z':b,
                          'possible_winners_under_independent_nonnegative_tail_mean':possible,
                          'unique_winner_guaranteed_by_this_bound':guaranteed[0] if len(guaranteed)==1 else None,
                          'assumption_is_observationally_calibrated':False,
                          'per_model_full_score_bounds':intervals})
    return {'models_in_window_descending':order,
            'in_window_scores':score,
            'in_window_top_model':leader,
            'in_window_runner_up':runner,
            'in_window_top_two_full_prior_contribution_gap':gap,
            'min_competitor_extra_unknown_tail_mean_to_reverse_if_leader_tail_is_zero':reversal_threshold,
            'threshold_not_a_measured_tail_likelihood':True,
            'possible_winner_scenarios':scenarios}


def analyze(data):
    w,q=validate_source(data)
    surfaces={k:one_surface(v,w,q) for k,v in sorted(data['surfaces'].items())}
    thresholds=[s['min_competitor_extra_unknown_tail_mean_to_reverse_if_leader_tail_is_zero'] for s in surfaces.values()]
    top={name:s['in_window_top_model'] for name,s in surfaces.items()}
    return {'schema':'J0740_F58_SEVEN_F42_CANDIDATES_COMMON_MASS_PRIOR_TAIL_PARTIAL_IDENTIFICATION_V1',
            'status':'PASS_MATHEMATICAL_PRIOR_TAIL_SENSITIVITY_NOT_EOS_POSTERIOR',
            'F51_expected_source_json_sha256':PINNED_F51_JSON_SHA256,
            'source_168_genuine_C_GR_star_values_reused_not_recomputed':True,
            'mass_window_all_seven_msun':list(EXPECTED_MASS_WINDOW),
            'known_common_radio_prior_mass_fraction':w,
            'unknown_radio_prior_mass_fraction':q,
            'mathematical_decomposition':'S_i=w*L_i_common_window+(1-w)*T_i_outside_window',
            'unknown_T_i':('Unknown nonnegative radio-prior-conditional average of source-corrected likelihood '
                           'outside the common window, if an EOS-specific physically admissible star branch and mass prior are supplied'),
            'lowest_top_two_reversal_threshold_over_six_surfaces':min(thresholds),
            'highest_top_two_reversal_threshold_over_six_surfaces':max(thresholds),
            'top_models_on_common_window_only':top,
            'surfaces':surfaces,
            'hard_science_boundary':{
                'unknown_mass_tail_has_measured_likelihood':False,
                'finite_upper_bound_on_tail_from_F51_data':'NOT_ESTABLISHED',
                'physical_stability_of_all_seven_models':'NOT_ESTABLISHED',
                'all_seven_are_original_nuclear_EOS':False,
                'native_joint_XPSI_source_refit':'NOT_RUN',
                'seven_source_native_physical_EOS_Bayes':'NOT_RUN',
                'two_salmi_huang_2026_photon_sets_independent':False,
                'ranking_identifiable_with_nonnegative_but_unbounded_tail':False,
                'no_reuse_as_full_EOS_evidence':True,
                'interpretation':'Sensitivity of already-calculated F51 conditional source-corrected KDE scores. No new stars, no new NICER photons, no justified full-prior EOS posterior. The B cap is hypothetical, not observed.'
            }}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--f51',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if sha256(args.f51)!=PINNED_F51_JSON_SHA256:
        raise ValueError('F58_F51_RESULTS_SHA256_DRIFT')
    result=analyze(json.loads(args.f51.read_text()))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],
                      'w':result['known_common_radio_prior_mass_fraction'],
                      'q':result['unknown_radio_prior_mass_fraction'],
                      'minimum_reversal_tail_mean':result['lowest_top_two_reversal_threshold_over_six_surfaces'],
                      'surfaces':{k:{'leader':s['in_window_top_model'],
                                     'runner':s['in_window_runner_up'],
                                     'critical_tail_mean':s['min_competitor_extra_unknown_tail_mean_to_reverse_if_leader_tail_is_zero']}
                                  for k,s in result['surfaces'].items()}},sort_keys=True),flush=True)

if __name__=='__main__': main()