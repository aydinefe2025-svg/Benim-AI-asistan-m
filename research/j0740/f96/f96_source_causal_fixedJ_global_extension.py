#!/usr/bin/env python3
"""F96: genuine compiled Einstein C/RNS at one COMMON fixed J across two meshes.

All central densities are strictly below the FIRST native CompOSE APR causality
violation. This is a conservative source-limited rotating equilibrium sequence,
not a GR dynamical eigenmode calculation or global EOS microphysical validation.

The original F88/F89 results are READ as provenance and reused; no original
five-point samples are rerun for their old J targets. This new comparison uses
one fixed J and the SAME absolute central density in both meshes.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path

PUBLISHER_SHA='8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12'
F89_GRIDS=('151x301','201x401')
LOW_FRACTIONS=(-.12,-.09,-.06,-.03,0.,.025,.035,.040)
CAUSAL_MARGIN=.005


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def choose_grid(baselines:dict,acausal_rho:float):
    """Predeclared fractions and final one 0.5% below the source acausal limit."""
    if set(baselines)!=set(F89_GRIDS) or not math.isfinite(acausal_rho):
        raise ValueError('ORIGINAL_C_BASELINES_REQUIRED')
    rho_ref=sum(baselines[g]['rho_c_g_cm3'] for g in F89_GRIDS)/2
    j_ref=math.sqrt(math.prod(baselines[g]['J_cgs'] for g in F89_GRIDS))
    frac_edge=acausal_rho*(1-CAUSAL_MARGIN)/rho_ref-1
    if frac_edge<=max(LOW_FRACTIONS):
        raise ValueError('NO_CAUSAL_REGION_AFTER_0p04_SAMPLED_GRID')
    factors=tuple(sorted(set(LOW_FRACTIONS+(frac_edge,))))
    densities=tuple(rho_ref*(1+x) for x in factors)
    assert len(densities)==len(factors)==9
    assert all(1e14<rho<acausal_rho for rho in densities)
    return rho_ref,j_ref,factors,densities


def verify_input(f88:dict,f89:dict,eos:Path,binaries:dict):
    if f88['audit']['original_COMPOSE_APR_sha256']!=PUBLISHER_SHA:
        raise ValueError('F88_REAL_COMPOSE_SOURCE_SHA_DRIFT')
    if f88['audit']['source_referenced_high_density_superluminal_nodes']!=24:
        raise ValueError('DO_NOT_HIDE_ORIGINAL_ACAUSAL_NODES')
    if sha(eos)!=f88['audit']['derived_F88_RNS_SHA256']:
        raise ValueError('F88_EOS_SURFACE_EXTENSION_BYTES_CHANGED')
    if set(binaries)!=set(F89_GRIDS):
        raise ValueError('NEED_TWO_INDEPENDENT_C_GRIDS')
    if {g:sha(binaries[g]) for g in F89_GRIDS}!=f88['binary_sha256']:
        raise ValueError('F88_COMPILED_C_BINARY_HASH_CHANGED')
    if f89['publisher_original_SHA256']!=PUBLISHER_SHA:
        raise ValueError('F89_ORIGINAL_SOURCE_DRIFT')
    if f89['F88_source_C_binary_sha256']!=f88['binary_sha256']:
        raise ValueError('F89_REFERENCE_GRIDS_MISMATCH')
    if not set(F89_GRIDS)==set(f88['actual_C_stars'])==set(f89['grid_results']):
        raise ValueError('NO_SOURCE_OLD_BENCHMARK')
    for g in F89_GRIDS:
        old=f89['grid_results'][g]
        if not(old['mass_strict_increasing'] and len(old['points'])==5):
            raise ValueError('F89_FIVE_POINT_BENCHMARK_NOT_POSITIVE')
        b=f88['actual_C_stars'][g]
        if abs(b['J_cgs']/old['target_J_cgs']-1)>1e-10:
            raise ValueError('F89_BASELINE_J_NOT_SOURCE_LOCKED')
    bounds={g:f88['audit']['grids'][g]['causal_e_c_upper_g_cm3'] for g in F89_GRIDS}
    if abs(bounds[F89_GRIDS[0]]/bounds[F89_GRIDS[1]]-1)>1e-12:
        raise ValueError('SOURCE_CAUSAL_THRESHOLD_NOT_COMMON')
    return choose_grid(f88['actual_C_stars'],bounds[F89_GRIDS[0]])+(bounds[F89_GRIDS[0]],)


def evaluate_grid(read_C, f89_module, baseline, target_j, densities, causal_upper, journal:Path):
    """Real source C evaluator; strictly fail-shut and persist every actual C call."""
    from scipy.optimize import brentq
    command=float(baseline['commanded_f_hz'])
    records=[]; errors=[]
    for k,rho in enumerate(densities):
        seen=[]
        def watched(lr,cmd):
            try:
                x=read_C(lr,cmd)
                seen.append({'central_rho_g_cm3':float(10**lr), 'commanded_f_hz':float(cmd),
                    'measured_M_Msun':x['M_msun'],'measured_J_cgs':x['J_cgs'],
                    'measured_spin_hz':x['spin_hz'],'real_C_solver':x['real_C_solver']})
            except Exception as exc:
                seen.append({'central_rho_g_cm3':float(10**lr), 'commanded_f_hz':float(cmd),
                    'actual_C_error':str(exc)})
                with journal.open('a',encoding='utf8') as out:
                    out.write(json.dumps({'point_index':k,'record':seen[-1]},allow_nan=False)+'\n')
                raise
            with journal.open('a',encoding='utf8') as out:
                out.write(json.dumps({'point_index':k,'record':seen[-1]},allow_nan=False)+'\n')
            return x
        try:
            rec=f89_module.root_at_fixed_j(watched,rho,command,target_j,causal_upper)
            rec['source_point_index']=k
            rec['measured_J_matches_common_target']=True
            rec['actual_native_C_calls_recorded']=len(seen)
            if rec['actual_native_C_calls_recorded']!=rec['direct_C_evaluations']:
                raise RuntimeError('ACTUAL_RNS_C_TRACE_COUNT_MISMATCH')
            command=rec['f_commanded_hz']
            records.append(rec)
        except Exception as exc:
            errors.append({'point_index':k,'rho_g_cm3':rho,'error':str(exc),'attempted_native_C_calls':len(seen)})
            print('F96_REAL_C_POINT_FAILED',json.dumps(errors[-1]),flush=True)
    return records,errors


def audit_result(model, data):
    factors=data['fractional_central_rho_grid'];dens=data['density_grid_g_cm3']
    both=data['two_grid_native_results'];bounds=data['first_source_acausal_rho_g_cm3']
    if not(len(factors)==len(dens)==9 and max(dens)<bounds and data['first_source_acausal_nodes']==24):
        raise ValueError('F96_UNPHYSICAL_CAUSAL_GRID')
    if set(both)!=set(F89_GRIDS):raise ValueError('F96_MISSING_GRID')
    data['sampled_causal_derivative_signs']={}
    for grid,entry in both.items():
        stars=entry['completed_actual_C_stars'];errors=entry['errors']
        if any(not x['real_solver_checked'] for x in stars):raise ValueError('F96_SYNTHETIC_C_SOURCE_REJECTED')
        if len({x['source_point_index'] for x in stars})!=len(stars):raise ValueError('DUPLICATE_NATIVE_C_POINT')
        if len(stars)+len(errors)!=9:raise ValueError('F96_MISSING_NATIVE_RESULT')
        if any(x['J_relative_error']>3e-5 for x in stars):raise ValueError('F96_MISMATCH_COMMON_PHYSICAL_J')
        sample=sorted(stars,key=lambda x:x['reported_rho_g_cm3'])
        slopes=[(y['M_msun']-x['M_msun'])/(y['reported_rho_g_cm3']/data['central_rho_common_reference_g_cm3']-x['reported_rho_g_cm3']/data['central_rho_common_reference_g_cm3']) for x,y in zip(sample,sample[1:])]
        data['sampled_causal_derivative_signs'][grid]={'interval_M_rho_slopes':slopes,
           'all_sampled_intervals_positive':len(sample)==9 and all(s>0 for s in slopes),
           'any_sampled_negative_slope':any(s<=0 for s in slopes),
           'minimum_measured_slope':min(slopes) if slopes else None,
           'number_of_fully_tested_source_real_C_stars':len(stars)}
    paired=[]
    for a,b in zip(both[F89_GRIDS[0]]['completed_actual_C_stars'],both[F89_GRIDS[1]]['completed_actual_C_stars']):
        if a['source_point_index']!=b['source_point_index']:continue
        paired.append({'point':a['source_point_index'],
             'M_difference_Msun':a['M_msun']-b['M_msun'],
             'R_eq_difference_m':(a['R_eq_km']-b['R_eq_km'])*1e3,
             'relative_J_error_between_grids':a['J_measured_cgs']/b['J_measured_cgs']-1})
    data['cross_grid_common_density_common_J_comparison']=paired
    data['causal_sampled_coverage_status']='TWO_GRIDS_FULL_SOURCE_CAUSAL_SAMPLE_SCAN' if all(len(both[g]['completed_actual_C_stars'])==9 for g in F89_GRIDS) else 'PARTIAL_FAILED_POINTS_NOT_OVERCLAIMED'
    data['rotating_axisymmetric_dyn_eigenmode']='NOT_RUN'
    data['continuous_global_fixed_J_turning_proof']='NOT_PROVEN_BY_DISCRETE_SAMPLES'
    data['seventh_EOS_full_native_photon_Bayes']='NOT_RUN'
    data['source_EOS_global_causality']='NOT_CERTIFIED_HIGH_DENSITY_SUPERLUMINAL_SOURCE_NODES_PRESERVED'
    return data


def main(args):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f89'))
    import f89_fixed_j_real_rns as f89
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f81'))
    import f81_exact_mass_spin as F81
    f88=json.loads(Path(args.f88).read_text(encoding='utf8'))
    f89old=json.loads(Path(args.f89).read_text(encoding='utf8'))
    bins={'151x301':Path(args.rns151),'201x401':Path(args.rns201)}
    rho0,j,factors,densities,upper=verify_input(f88,f89old,Path(args.eos),bins)
    report={'schema':'J0740_F96_REAL_ORIGINAL_APR_SOURCE_CAUSAL_RANGE_COMMON_J_DUAL_RNS_C_V1',
        'status':'IN_PROGRESS_ORIGINAL_CAUSAL_SOURCE_MESH_STARS',
        'source_original_Zenodo_SHA256':PUBLISHER_SHA,
        'original_C_compiler_binary_SHA256':f88['binary_sha256'],
        'real_source_rns_eos_SHA256':sha(args.eos),
        'F88_input_receipt_SHA256':sha(args.f88),'F89_5x2_native_reference_SHA256':sha(args.f89),
        'fixed_same_common_J_cgs':j,'central_rho_common_reference_g_cm3':rho0,
        'fractional_central_rho_grid':factors,'density_grid_g_cm3':densities,
        'first_source_acausal_rho_g_cm3':upper,'first_source_acausal_nodes':24,
        'underlying_f88_low_density_source_extension':'PRESENT_100_ADDITIONAL_LOW_DENSITY_ROWS_EXPLICIT',
        'two_grid_native_results':{},'original_seven_EOS_LAL_source_physical_certification':'NOT_RUN',
        'XPSI_native_photon_calls_in_this_run':0}
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    for grid in F89_GRIDS:
        journal=out.parent/('F96_NATIVE_C_trace_'+grid+'.jsonl')
        if journal.exists():raise FileExistsError('F96 refuse to overwrite previous real C trace '+str(journal))
        def observed(lr,fc,b=bins[grid]):return F81.evaluate_rns(b,Path(args.eos),lr,fc)
        points,errors=evaluate_grid(observed,f89,f88['actual_C_stars'][grid],j,densities,upper,journal)
        report['two_grid_native_results'][grid]={'completed_actual_C_stars':points,'errors':errors,
             'native_C_calls_logged_in_trace':len(journal.read_text().splitlines()) if journal.exists() else 0,
             'trace_SHA256':sha(journal) if journal.exists() else None}
        out.write_text(json.dumps(report,indent=2,allow_nan=False,sort_keys=True)+'\n')
        print('F96_SOURCE_PINNED_NATIVE_C_GRID_FINISHED',grid,json.dumps({'successful':len(points),'failed':len(errors),'native_evaluations':report['two_grid_native_results'][grid]['native_C_calls_logged_in_trace']}),flush=True)
    report=audit_result(None,report)
    report['status']=('TWO_GRID_ACTUAL_RNS_COMPLETE_CAUSAL_RANGE_DISCRETE_ONLY' if report['causal_sampled_coverage_status']=='TWO_GRIDS_FULL_SOURCE_CAUSAL_SAMPLE_SCAN' else 'PARTIAL_REAL_C_MISSING_SOME_DENSITIES')
    out.write_text(json.dumps(report,indent=2,allow_nan=False,sort_keys=True)+'\n')
    print('F96_NATIVE_SOURCE_RESULT',json.dumps({'status':report['status'],'sampled_slopes':report['sampled_causal_derivative_signs'],'cross_mesh_pairs':len(report['cross_grid_common_density_common_J_comparison'])}),flush=True)
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for name in ('f88','f89','eos','rns151','rns201','out'):ap.add_argument('--'+name,required=True)
    main(ap.parse_args())