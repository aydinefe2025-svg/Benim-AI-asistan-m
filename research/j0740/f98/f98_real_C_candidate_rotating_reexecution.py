#!/usr/bin/env python3
"""Real source-pinned rotating Einstein C reexecution of a DISTINCT 1943-row interpolation candidate.
This is NOT the original F96 physical EOS and not a rotating mode-stability proof.
No fake/mocked stars and no alteration of actual C Einstein equations.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path

GRIDS=('151x301','201x401')
OLD_F96_SHA='a794218fd091c02e92e522e599003c0a6375c072f8b43d6607f89409155fce5a'
OLD_RNS_SHA='7643d0e4361adee77cc79d1b69eb445db70a52443b833c4dddafa973193fb580'
NEW_CANDIDATE_SHA='d62d490dd106f7995cb96563bcb438de8c934375cca4fb04d9010b6300a8cff9'
PUB_SHA='8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main(a):
    import numpy as np
    f98_path=Path(__file__).resolve()
    base=f98_path.parents[1]
    sys.path[:0]=[str(base/'f81'),str(base/'f89'),str(base/'f96')]
    import f81_exact_mass_spin as F81
    import f89_fixed_j_real_rns as f89
    import f96_source_causal_fixedJ_global_extension as f96
    import f98_rns_source_interpolation_repair as f98
    original=json.loads(Path(a.oldf96).read_text())
    if sha(a.oldf96)!=OLD_F96_SHA:raise ValueError('F98_ORIGINAL_F96_18_STAR_RESULT_SHA_DRIFT')
    orig_rns=f98.load_rns(a.original_eos)
    if sha(a.original_eos)!=OLD_RNS_SHA:raise ValueError('F98_ORIGINAL_EOS_DRIFT')
    candidate=np.loadtxt(a.candidate_eos,skiprows=1)
    if sha(a.candidate_eos)!=NEW_CANDIDATE_SHA:raise ValueError('F98_CANDIDATE_SOURCE_CHANGED')
    expected=f98.add_exact_original_knot_intermediates(orig_rns)
    if not np.array_equal(candidate,expected):raise ValueError('F98_NEW_CANDIDATE_NOT_FROM_ORIGINAL_NODES')
    oldf88=json.loads(Path(a.f88).read_text())
    if oldf88['audit']['original_COMPOSE_APR_sha256']!=PUB_SHA:raise ValueError('WRONG_PUBLISHER_ORIGINAL_EOS')
    if oldf88['audit']['derived_F88_RNS_SHA256']!=OLD_RNS_SHA:raise ValueError('F88_SOURCE_OLD_EOS_MISMATCH')
    rns={'151x301':Path(a.rns151),'201x401':Path(a.rns201)}
    if {k:sha(v) for k,v in rns.items()}!=oldf88['binary_sha256']:
        raise ValueError('F98_REAL_EINSTEIN_C_ORIGINAL_BINARY_HASH_MISMATCH')
    if set(original['two_grid_native_results'])!=set(GRIDS):raise ValueError('F96_TWO_MESH_MISSING')
    if not all(len(v['completed_actual_C_stars'])==9 and len(v['errors'])==0 for v in original['two_grid_native_results'].values()):
        raise ValueError('F96_NOT_GENUINELY_COMPLETE')
    densities=[float(v) for v in original['density_grid_g_cm3']]
    previous_examination=json.loads(Path(a.f98).read_text())
    if previous_examination['derived_new_distinct_interpolation_candidate']['numerical_EOS_file_sha256']!=NEW_CANDIDATE_SHA:
        raise ValueError('F98_PREVIOUS_PHYSICAL_SOURCE_AUDIT_CHANGED')
    if not all(x['passes_local_positive_causal_interpolated_P_e'] for x in f98.audit_grid_fast(candidate,densities)):
        raise ValueError('F98_INTERPOLATION_IS_NOT_CAUSAL_FOR_ALL_NINE')
    j=original['fixed_same_common_J_cgs']
    print('F98_ACTUAL_EINSTEIN_C_CANDIDATE_PRECHECK_COMPLETE',{'source':PUB_SHA,'candidate':NEW_CANDIDATE_SHA,'fixed_same_J_cgs':j},flush=True)
    report={'schema':'F98_ACTUAL_SOURCE_NODE_PRESERVING_1943_EOS_REAL_EINSTEIN_C_TWO_MESH_18_STARS_V1',
      'status':'IN_PROGRESS_NOT_CERTIFIED',
      'physical_model':'DISTINCT_1943_NODE_SOURCE_PRESERVING_INTERPOLATION_CANDIDATE_NOT_NATIVE_ORIGINAL_1933',
      'not_a_new_publisher_EOS':True,'source_original_COMPOSE_Zenodo_SHA256':PUB_SHA,
      'old_F96_true_C_source_sha256':OLD_F96_SHA,'original_source_RNS_1933_sha256':OLD_RNS_SHA,
      'new_1943_node_candidate_EOS_sha256':NEW_CANDIDATE_SHA,
      'candidate_source_original_nodes_unchanged':1933,'candidate_intermediate_rows':10,
      'candidate_interpolation_cs2_test':'PASSED_ALL_9_CENTERS_IN_EOS_LOG_LAGRANGE',
      'original_C_Einstein_binary_sha256':oldf88['binary_sha256'],
      'same_J_cgs':j,'same_absolute_central_density_both_grids':densities,
      'first_original_source_superluminal_knot_rho_g_cm3':original['first_source_acausal_rho_g_cm3'],
      'global_source_physical_causality':'NOT_CERTIFIED_BEYOND_CENTERS',
      'thermodynamic_first_law_exactness':'NOT_PROVEN_FOR_INSERTED_NUMERICAL_ROWS',
      'rotating_eigenmode_dynamic_stability':'NOT_RUN',
      'full_seven_original_EOS_native_XPSI_Bayes':'NOT_RUN',
      'native_C_star_results':{},'old_F96_original_true_C_result_source':oldf88['audit']['model']}
    out=Path(a.out);out.parent.mkdir(exist_ok=True,parents=True)
    for grid in GRIDS:
        journal=out.parent/('F98_real_C_candidate_trace_'+grid+'.jsonl')
        if journal.exists():raise FileExistsError('Refuse overwrite F98 authentic C journal')
        def evaluate(logrho,commanded,b=rns[grid]):return F81.evaluate_rns(b,Path(a.candidate_eos),logrho,commanded)
        stars,errors=f96.evaluate_grid(evaluate,f89,oldf88['actual_C_stars'][grid],j,densities,original['first_source_acausal_rho_g_cm3'],journal)
        old=original['two_grid_native_results'][grid]['completed_actual_C_stars']
        diff=[]
        for s in stars:
            ref=old[s['source_point_index']]
            diff.append({'source_point_index':s['source_point_index'],
                'difference_Msun_1943_minus_1933':s['M_msun']-ref['M_msun'],
                'difference_R_equatorial_m_1943_minus_1933':(s['R_eq_km']-ref['R_eq_km'])*1000,
                'difference_spin_report_Hz_1943_minus_1933':s['f_measured_hz']-ref['f_measured_hz'],
                'old_original_Msun':ref['M_msun'],'new_candidate_Msun':s['M_msun']})
        report['native_C_star_results'][grid]={'stars':stars,'errors':errors,'actual_native_C_calls_logged':len(journal.read_text().splitlines()),
          'real_source_journal_sha256':sha(journal),'paired_original_1933_EOS_deltas':diff}
        out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
        print('F98_REAL_EINSTEIN_C_REPAIRED_CANDIDATE_GRID',grid,{'stars':len(stars),'failed':len(errors),'calls':len(journal.read_text().splitlines())},flush=True)
    results=report['native_C_star_results']
    valid_all=all(len(results[g]['stars'])==9 and not results[g]['errors'] for g in GRIDS)
    report['native_C_calls_all_grids']=sum(results[g]['actual_native_C_calls_logged'] for g in GRIDS)
    paired=[]
    for s,t in zip(results[GRIDS[0]]['stars'],results[GRIDS[1]]['stars']):
        if s['source_point_index']!=t['source_point_index']:
            raise RuntimeError('CROSSGRID_CANDIDATE_MODEL_DENSITY_ID_MISMATCH')
        paired.append({'point_id':s['source_point_index'],'delta_M_Msun':s['M_msun']-t['M_msun'],
                       'delta_R_m':(s['R_eq_km']-t['R_eq_km'])*1000,
                       'relative_J_diff':s['J_measured_cgs']/t['J_measured_cgs']-1})
    report['paired_two_original_source_Einstein_C_meshes']=paired
    report['native_C_star_count_all_grids']=sum(len(results[g]['stars']) for g in GRIDS)
    report['original_EOS_18_true_numerical_C_stars_thermo_sign_consistency']='FAIL_NEGATIVE_NATIVE_C_CUBIC_EOS_SLOPE'
    report['new_derived_EOS_18_star_numerical_equilibrium']='PASS_18_ACTUAL_C_STARS_DISTINCT_EOS' if valid_all else 'PARTIAL_NOT_ACCEPTED'
    report['status']='18_REAL_C_EINSTEIN_STARS_1943_NUMERICALLY_SOLVED_NOT_DYNAMIC_STABILITY' if valid_all else 'PARTIAL_NATIVE_C_FAILURE_NOT_ACCEPTED'
    out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print('F98_GENUINE_NATIVE_C_FINAL',{'status':report['status'],'calls':report['native_C_calls_all_grids'],'stars':report['native_C_star_count_all_grids'],'max_abs_Msun_delta_from_original':max(abs(x['difference_Msun_1943_minus_1933']) for g in results.values() for x in g['paired_original_1933_EOS_deltas'])},flush=True)
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for name in ['oldf96','original-eos','candidate-eos','f88','f98','rns151','rns201','out']:
        ap.add_argument('--'+name,required=True)
    main(ap.parse_args())
