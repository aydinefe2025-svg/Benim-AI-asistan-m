#!/usr/bin/env python3
"""F101: source-locked rescue of FOUR failed F100 C-RNS fixed-J roots ONLY.

Never recomputes or replaces 24 valid F100 source C stars. The old F100 partial
report and its raw C logs are preserved byte-exact, including original errors.
Only the upstream findmodel.c::SetSpin scalar numerical bracket precision may
change (float => double, xacc=1e-9). No Einstein equations or physical EOS changes.
Even successful 28/28 is *discrete* rotating stationary M(rho)|J evidence only,
NOT a 2D GR dynamical normal-mode calculation and NOT original 7-EOS Bayes.
"""
from __future__ import annotations
import argparse,hashlib,json,sys,math
from pathlib import Path
import numpy as np

EXPECTED_ORIGINAL_F100_SHA='2f60a33262319a50af39d03641eb0a52375037450964d0f3206ae8687712506f'
EOS_SHA='c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
OLD_SOURCES={'151x301':13,'201x401':11}
FAILS={'151x301':(12,), '201x401':(6,11,12)}
TARGET_TOTAL_STARS=28
GRIDS=('151x301','201x401')

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def source_report_checks(original:dict):
    assert original['status']=='REAL_C_PARTIAL_NOT_PHYSICS_ACCEPTED'
    assert original['native_real_C_stars']==24 and original['new_native_C_calls']==399
    assert original['derived_F99_eos_sha256']==EOS_SHA
    for grid in GRIDS:
        g=original['two_grid_results'][grid]
        assert len(g['actual_C_stars'])==OLD_SOURCES[grid]
        assert tuple(e['source_point_index'] for e in g['real_C_errors'])==FAILS[grid]
        assert all(x['real_solver_checked'] and x['J_relative_error']<=3e-5 for x in g['actual_C_stars'])
        assert len({s['source_point_index'] for s in g['actual_C_stars']})==OLD_SOURCES[grid]
        assert {x['source_point_index'] for x in g['actual_C_stars']}.isdisjoint(FAILS[grid])
    assert len(original['predeclared_central_densities_g_cm3'])==14
    return True

def combine(original:dict, rescueds:dict, new_calls:dict, native_C_sha:dict):
    source_report_checks(original)
    result={
        'schema':'F101_F100_ORIGINAL_399_CALLS_24_STARS_PLUS_FOUR_PRECISION_ONLY_NEW_REAL_C_GR_STARS_V1',
        'status':'INCOMPLETE_REQUIRE_FOUR_ACTUAL_NEW_EINSTEIN_C_ROOTS',
        'original_failed_F100_C_24star_receipt_sha256':EXPECTED_ORIGINAL_F100_SHA,
        'original_F100_24_existing_stars_immutable':True,
        'original_399_C_calls_untouched':True,
        'original_F100_four_J_mismatch_failures_UNALTERED':{
            k:original['two_grid_results'][k]['real_C_errors'] for k in GRIDS},
        'candidate_change':'ONLY_upstream_RNS_SetSpin_Ridder_float_to_double_xacc_1e-9_and_F81_stdout_print_only',
        'Einstein_field_equations_modified':False,
        'EOS_modified':False,
        'physical_fixed_J_or_eccentricity_changed':False,
        'accept_J_relative_error_le':3e-5,
        'source_derived_cold_F99_EOS_SHA256':EOS_SHA,
        'original_F100_fixed_J_cgs':original['target_same_J_cgs'],
        'same_14_pregistered_central_densities':original['predeclared_central_densities_g_cm3'],
        'original_C_work':{'stars':24,'calls':399},
        'new_C_calls':new_calls,
        'patched_C_binary_sha256':native_C_sha,
        'old_and_new_28_real_C_stars':{},
        'discrete_same_J_turning_point':'PENDING_ONLY_IF_ALL_FOUR_ROOTS_SUCCESS',
        'rotating_2D_GR_axisymmetric_dynamic_mode_eigenfrequencies':'NOT_RUN',
        'full_source_seven_EOS_XPSI_MR_Bayesian_evidence':'NOT_RUN',
        'F100_static_true_GR_radial_eigenmode_zero':'REAL_COMPLETED_SEPARATE_J0_MODEL'}
    for grid in GRIDS:
        old=original['two_grid_results'][grid]['actual_C_stars']
        newer=rescueds[grid]
        missing=set(FAILS[grid]); present={r['source_point_index'] for r in newer}
        if present!=missing:raise ValueError('FOUR_ACTUAL_C_FAILURE_RESCUE_UNRESOLVED '+grid+' '+str(missing-present))
        for rec in newer:
            i=rec['source_point_index']
            if not (rec['real_solver_checked'] and rec['J_relative_error']<=3e-5):
                raise ValueError('REAL_NATIVE_C_SOURCE_J_NOT_CERTIFIED '+grid+' '+str(i))
            if not math.isclose(rec['requested_rho_g_cm3'], original['predeclared_central_densities_g_cm3'][i],rel_tol=1e-13):
                raise ValueError('PHYSICAL_RHO_DRIFT')
            if not math.isclose(rec['J_target_cgs'],original['target_same_J_cgs'],rel_tol=1e-14):
                raise ValueError('PHYSICAL_J_DRIFT')
        both=sorted(old+newer,key=lambda x:x['source_point_index'])
        if [r['source_point_index'] for r in both]!=list(range(14)):raise ValueError('ORIGINAL_14_POINTS_NOT_COVERED')
        arr=np.asarray([x['M_msun'] for x in both]);rho=np.asarray([x['reported_rho_g_cm3'] for x in both]);
        if not np.all(np.diff(rho)>0):raise ValueError('NONMONOTONIC_SOURCE_CENTERS')
        dM=np.diff(arr)/np.diff(rho/1e15)
        if not (np.any(dM>0) and np.any(dM<0) and 1<np.argmax(arr)<12):
            raise ValueError('NO_DIRECT_C_PHYSICAL_SAMPLED_TURNING')
        if not all(x['real_solver_checked'] and x['J_relative_error']<=3e-5 for x in both):
            raise ValueError('INVALID_REAL_C_ORIGINAL_PLUS_RECOVERED')
        result['old_and_new_28_real_C_stars'][grid]={
            'n_old_original_C':len(old),'n_new_patched_precision_C':len(newer),
            'old_C_original_source_records_reused_NOT_REEVALUATED':True,
            'stars':both, 'sample_dM_per_rho15':dM.tolist(),
            'sample_max_mass_Msun':float(np.max(arr)),
            'sample_peak_central_rho_g_cm3':float(rho[np.argmax(arr)]),
            'sampled_positive_then_negative_slope':bool(np.any((dM[:-1]>0)&(dM[1:]<0))),
            'continuous_turning_point_proven':'NO_DISCRETE_SAMPLES_ONLY',
            'dynamical_mode_calculated':'NO'}
    if not all(v['sampled_positive_then_negative_slope'] for v in result['old_and_new_28_real_C_stars'].values()):
        raise ValueError('SAMPLED_ROTATING_FIXED_J_MAX_NOT_CONFIRMED')
    result['status']='28_TWO_C_MESH_SAMPLED_SAME_J_MASS_TURN_PHYSICS_NUMERIC_PASS_NOT_DYNAMIC_MODES'
    result['discrete_same_J_turning_point']='YES_BOTH_NATIVE_C_MESHES_FINITE_DIFFERENCE_SIGNCHANGE'
    result['total_source_C_stars']=TARGET_TOTAL_STARS
    result['total_old_plus_new_actual_C_calls']=399+sum(new_calls.values())
    return result

def main(args):
    if sha(args.original)!=EXPECTED_ORIGINAL_F100_SHA:raise ValueError('ORIGINAL_REAL_F100_24_STAR_BINARY_SHA_DRIFT')
    if sha(args.eos)!=EOS_SHA:raise ValueError('DERIVED_F99_EOS_NOT_IDENTICAL')
    old=json.loads(Path(args.original).read_text())
    source_report_checks(old)
    sys.path[:0]=[str(Path(__file__).resolve().parents[1]/f) for f in ('f81','f89')]
    import f81_exact_mass_spin as F81
    import f89_fixed_j_real_rns as F89
    paths={'151x301':Path(args.rns151),'201x401':Path(args.rns201)}
    if any(not v.is_file() for v in paths.values()):raise ValueError('MISSING_TWO_NATIVE_C_BINARIES')
    if sha(paths['151x301'])==sha(paths['201x401']):raise ValueError('IDENTICAL_C_GRID_BINARIES')
    output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
    rescues={};call_counts={};failures={}
    for grid in GRIDS:
        originals={x['source_point_index']:x for x in old['two_grid_results'][grid]['actual_C_stars']}
        trace=output.parent/f'F101_ONLY_MISSING_ORIGINAL_F100_REAL_C_{grid}.jsonl'
        if trace.exists():raise FileExistsError('FAIL_CLOSED_CANNOT_OVERWRITE_NATIVE_SOURCE_LOG')
        new=[];fail=[];counter=0
        for index in FAILS[grid]:
            rho=old['predeclared_central_densities_g_cm3'][index]
            prior_index=max(i for i in originals if i<index)
            prior_cmd=originals[prior_index]['f_commanded_hz']
            def evaluate(logrho,comm):
                nonlocal counter
                try:
                    star=F81.evaluate_rns(paths[grid],Path(args.eos),logrho,comm)
                    rec={'source_point_index':index,'rho_g_cm3':rho,'requested_spin_hz':float(comm),
                         'actual_native_C':True,'M_msun':star['M_msun'],'J_cgs':star['J_cgs'],
                         'f_reported_hz':star['spin_hz'],'R_eq_km':star['R_equatorial_km']}
                except Exception as e:
                    rec={'source_point_index':index,'rho_g_cm3':rho,'requested_spin_hz':float(comm),
                         'actual_native_C_error':repr(e)}
                    with trace.open('a') as f:f.write(json.dumps(rec,allow_nan=False)+'\n')
                    counter+=1;raise
                with trace.open('a') as f:f.write(json.dumps(rec,allow_nan=False)+'\n')
                counter+=1
                return star
            before=counter
            try:
                rec=F89.root_at_fixed_j(evaluate,rho,prior_cmd,old['target_same_J_cgs'],3.60e15,real_required=True)
                rec['source_point_index']=index
                if rec['direct_C_evaluations']!=counter-before:raise ValueError('REAL_NATIVE_C_LOGGING_COUNT_MISMATCH')
                new.append(rec)
                print('F101_NEW_DIRECT_EINSTEIN_C_RECOVERED',grid,index,'M',rec['M_msun'],'Jerr',rec['J_relative_error'],'new_source_C_calls',counter-before,flush=True)
            except Exception as e:
                fail.append({'source_point_index':index,'error':repr(e),'C_calls':counter-before})
                print('F101_NEW_DIRECT_EINSTEIN_C_FAILURE_RETAINED',grid,index,repr(e),flush=True)
            output.write_text(json.dumps({'status':'IN_PROGRESS_NATIVE_C_NO_FALSE_SUCCESS',
               'original_24_stars_preserved':True,'old_failure_receipts_preserved':True,'grid':grid,
               'new_real_C_stars':new,'failures':fail,'new_native_C_calls':counter},indent=2,allow_nan=False)+'\n')
        rescues[grid]=new;failures[grid]=fail;call_counts[grid]=counter
    try:
        result=combine(old,rescues,call_counts,{k:sha(v) for k,v in paths.items()})
    except ValueError as e:
        result={'schema':'F101_SOURCE_NATIVE_REAL_C_RECOVERY_FAIL_CLOSED','status':'FOUR_C_ROOTS_NOT_ALL_PASS',
            'actual_old_C_success_stars':24,'actual_new_C_success_stars':sum(len(v) for v in rescues.values()),
            'failures':failures,'new_call_counts':call_counts,
            'original_4_source_failures_not_erased':True,'scientific_claim':'NOT_ACCEPTED',
            'actual_C_root_error':repr(e),'rotating_dynamic_modes':'NOT_RUN','full_native_EOS_Bayes':'NOT_RUN'}
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('F101_RECOVERY_SUMMARY',result['status'],json.dumps({'new_stars':sum(len(v) for v in rescues.values()),'new_C_calls':sum(call_counts.values())}),flush=True)
    if result['status']!='28_TWO_C_MESH_SAMPLED_SAME_J_MASS_TURN_PHYSICS_NUMERIC_PASS_NOT_DYNAMIC_MODES':
        raise SystemExit(2)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for key in ['original','eos','rns151','rns201','out']:ap.add_argument('--'+key,required=True)
    main(ap.parse_args())
