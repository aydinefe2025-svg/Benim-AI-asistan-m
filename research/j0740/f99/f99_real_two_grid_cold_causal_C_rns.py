#!/usr/bin/env python3
"""Genuine native C Einstein rotating stars at source-matched J and rho, on a distinct 1981-node cold causal derived APR model.

Original EOS is unchanged; any success demonstrates only the derived MODEL's
stationary RNS equilibria (NOT dynamic eigenmodes / photon Bayes).
"""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
GRIDS=('151x301','201x401')
SOURCE_F96_SHA='a794218fd091c02e92e522e599003c0a6375c072f8b43d6607f89409155fce5a'
SOURCE_F88_SHA='771d7b494821a43485a8e1248185e768efe9b26e10c0ac8d07b9c1c0f206bc36'
SOURCE_RNS_SHA='7643d0e4361adee77cc79d1b69eb445db70a52443b833c4dddafa973193fb580'
DERIVED_SHA='c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
PUBLISHER_SHA='8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main(a):
    sys.path[:0]=[str(Path(__file__).resolve().parents[1]/n) for n in ('f81','f89','f96','f98')]
    import f81_exact_mass_spin as F81
    import f89_fixed_j_real_rns as f89
    import f96_source_causal_fixedJ_global_extension as f96
    import f98_rns_source_interpolation_repair as f98
    if sha(a.oldf96)!=SOURCE_F96_SHA:raise ValueError('F96_SOURCE18STAR_SHA_MISMATCH')
    if sha(a.f88)!=SOURCE_F88_SHA:raise ValueError('F88_REAL_C_SOURCE_SHA_MISMATCH')
    if sha(a.original_eos)!=SOURCE_RNS_SHA:raise ValueError('SOURCE_ORIGINAL_RNS_SHA_MISMATCH')
    if sha(a.derived_eos)!=DERIVED_SHA:raise ValueError('DERIVED_COLD_1981_EOS_SHA_MISMATCH')
    f88=json.loads(Path(a.f88).read_text());old=json.loads(Path(a.oldf96).read_text());no=json.loads(Path(a.physics_receipt).read_text())
    if f88['audit']['original_COMPOSE_APR_sha256']!=PUBLISHER_SHA:raise ValueError('WRONG_PUBLISHER_SOURCE')
    if len(no['original_source_no_go']['exact_endpoints_no_go_intervals'])!=3:raise ValueError('NO_GO_NO_LONGER_PROVEN')
    d=no['derived_model']
    if d['output_SHA256']!=DERIVED_SHA or d['derived_nodes']!=1981 or d['max_affine_cs2']>1:
        raise ValueError('DERIVED_SOURCE_NOT_CAUSAL')
    if d['original_source_h_n_preserved'] or d['source_1933_original_rows_unchanged_in_derived_model']:
        raise ValueError('FALSE_ORIGINAL_SOURCE_CLAIM')
    arr=np.loadtxt(a.derived_eos,skiprows=1)
    if arr.shape!=(1981,4) or not np.all(np.diff(arr,axis=0)>0):raise ValueError('DERIVED_EOS_INVALID')
    densities=old['density_grid_g_cm3']
    scans=f98.audit_grid_fast(arr,densities)
    if not all(k['passes_local_positive_causal_interpolated_P_e'] for k in scans):
        raise ValueError('RNS_TRUE_C_4POINT_NEGATIVE_OR_SUPERLUMINAL')
    bins={'151x301':Path(a.rns151),'201x401':Path(a.rns201)}
    if {g:sha(bins[g]) for g in GRIDS}!=f88['binary_sha256']:
        raise ValueError('SOURCE_RNS_BINARY_SHA_MISMATCH')
    if set(old['two_grid_native_results'])!=set(GRIDS):raise ValueError('OLD_REAL_C_MISSING')
    for g in GRIDS:
        if len(old['two_grid_native_results'][g]['completed_actual_C_stars'])!=9 or old['two_grid_native_results'][g]['errors']:
            raise ValueError('ORIGINAL_NOT_18_NATIVE')
    j=old['fixed_same_common_J_cgs']
    report={'schema':'J0740_F99_DISTINCT_COLD_CAUSAL_DERIVED_1981_NODE_REAL_EINSTEIN_C_TWO_GRID_V1',
      'status':'IN_PROGRESS_NOT_ACCEPTED',
      'model':'DISTINCT_DERIVED_1981_NODE_THERMODYNAMICALLY_INTEGRATED_AFFINE_EOS_NOT_ORIGINAL_PUBLISHER',
      'source_original_publisher_zip_sha256':PUBLISHER_SHA,
      'source_original_C_RNS_eos_sha256':SOURCE_RNS_SHA,
      'source_original_F96_18realC_sha256':SOURCE_F96_SHA,
      'derived_distinct_1981_RNS_eos_sha256':DERIVED_SHA,
      'firstlaw_exact_piecewise_linear_input':'YES_NODE_RECURRENCE_FLOAT64',
      'native_C_interpolated_firstlaw_exact':'NOT_CERTIFIED_C_4PT_INTERPOLATES_COMPONENTS_SEPARATELY',
      'source_1933_original_thermodynamic_columns_preserved':'NO_DERIVED_MODEL',
      'original_source_3_exact_knots_firstlaw_causality_no_go':'PRESERVED_NOT_HIDDEN',
      'same_J_cgs_both_grids':j,'same_nine_original_density_g_cm3_both_grids':densities,
      'source_true_C_4pt_causal_preflight_all_nine':True,
      'rotating_axisymmetric_mode_stability':'NOT_RUN',
      'seven_EOS_full_photon_Bayes':'NOT_RUN',
      'grids':{}}
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    for g in GRIDS:
        journal=out.parent/('F99_real_native_C_trace_'+g+'.jsonl')
        if journal.exists():raise FileExistsError('REFUSE_OVERWRITE_REAL_C_SOURCE_DATA')
        observed=lambda lr,fc,b=bins[g]:F81.evaluate_rns(b,Path(a.derived_eos),lr,fc)
        stars,errors=f96.evaluate_grid(observed,f89,f88['actual_C_stars'][g],j,densities,
                                       old['first_source_acausal_rho_g_cm3'],journal)
        prior=old['two_grid_native_results'][g]['completed_actual_C_stars']
        deltas=[{'source_point_index':x['source_point_index'],
                 'new_minus_original_mass_Msun':x['M_msun']-prior[x['source_point_index']]['M_msun'],
                 'new_minus_original_equatorial_R_m':1000*(x['R_eq_km']-prior[x['source_point_index']]['R_eq_km'])}
               for x in stars]
        report['grids'][g]={'stars':stars,'errors':errors,
             'direct_C_calls':len(journal.read_text().splitlines()),'trace_sha256':sha(journal),
             'original_1933_source_native_deltas':deltas}
        out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
        print('F99_REAL_NATIVE_C_SOLVE',g,'stars',len(stars),'errors',len(errors),'calls',report['grids'][g]['direct_C_calls'],flush=True)
    good=all(len(report['grids'][g]['stars'])==9 and not report['grids'][g]['errors'] for g in GRIDS)
    report['number_of_real_C_stars']=sum(len(report['grids'][g]['stars']) for g in GRIDS)
    report['real_native_C_calls']=sum(report['grids'][g]['direct_C_calls'] for g in GRIDS)
    report['status']='18_ACTUAL_REAL_C_MODELS_ON_DISTINCT_DERIVED_1981_MODEL_NOT_ORIGINAL' if good else 'REAL_C_PARTIAL_FAILURE_NOT_ACCEPTED'
    out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print('F99_FINAL_NATIVE_PHYSICAL_NUMERICAL',report['status'],report['real_native_C_calls'],flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ['oldf96','original-eos','derived-eos','physics-receipt','f88','rns151','rns201','out']:p.add_argument('--'+n,required=True)
    main(p.parse_args())
