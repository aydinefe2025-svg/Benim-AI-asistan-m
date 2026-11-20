#!/usr/bin/env python3
"""F89: LOCAL constant-J M(rho_c) slope from genuine, source-pinned C/RNS stars.
Not full fixed-J turning-point classification, mode stability, or X-PSI Bayes.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path
from scipy.optimize import brentq

GRIDS=('151x301','201x401')
FACTORS=(-0.025,-0.0125,0.0,0.0125,0.025)
SOURCE_SHA='8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12'
J_REL_TOL=3e-5
BASE_J_REL_TOL=3e-4

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check_star(star,requested_rho,real_required=True):
    for key in ('M_msun','spin_hz','R_equatorial_km','J_cgs','rho_c_g_cm3'):
        if key not in star or not math.isfinite(float(star[key])) or float(star[key])<=0:
            raise ValueError('BAD_C_STAR_'+key)
    if real_required and star.get('real_C_solver') is not True:
        raise ValueError('SYNTHETIC_STAR_REJECTED_IN_PRODUCTION')
    if abs(star['rho_c_g_cm3']/requested_rho-1)>0.00015:
        raise ValueError('CENTRAL_DENSITY_NOT_ACTUAL_INPUT')
    if not 0<star['M_msun']<4 or not 100<star['spin_hz']<1200:
        raise ValueError('UNPHYSICAL_C_STAR_RANGE')
    return star

def root_at_fixed_j(evaluate,density,base_commanded_f,target_j,causal_upper,real_required=True):
    if not(1e13<density<causal_upper and 1e47<target_j<1e51):
        raise ValueError('DENSITY_OR_J_OUTSIDE_SOURCE_ACCEPTANCE')
    calls=[]
    def trial(commanded_f):
        s=check_star(evaluate(math.log10(density),commanded_f),density,real_required)
        calls.append({'requested_frequency_hz':float(commanded_f),
            'measured_frequency_hz':float(s['spin_hz']),
            'M_msun':float(s['M_msun']),'J_cgs':float(s['J_cgs']),
            'central_rho_g_cm3':float(s['rho_c_g_cm3'])})
        return s
    bracket=None
    for width in (15.0,35.0,70.0,125.0):
        lo=max(110.,base_commanded_f-width);hi=base_commanded_f+width
        left=trial(lo);right=trial(hi)
        if (left['J_cgs']-target_j)*(right['J_cgs']-target_j)<0:
            bracket=(lo,hi);break
    if bracket is None:raise RuntimeError('REAL_C_FIXED_J_NOT_BRACKETED')
    froot=brentq(lambda f:trial(f)['J_cgs']/target_j-1,*bracket,
                 xtol=.0002,rtol=1e-10,maxiter=35)
    star=trial(froot)
    error=abs(star['J_cgs']/target_j-1)
    if error>J_REL_TOL:raise RuntimeError('MEASURED_C_J_MISMATCH')
    return {'requested_rho_g_cm3':density,'reported_rho_g_cm3':star['rho_c_g_cm3'],
        'M_msun':star['M_msun'],'R_eq_km':star['R_equatorial_km'],
        'f_measured_hz':star['spin_hz'],'f_commanded_hz':float(froot),
        'J_measured_cgs':star['J_cgs'],'J_target_cgs':target_j,
        'J_relative_error':error,'direct_C_evaluations':len(calls),
        'evaluations':calls,'real_solver_checked':real_required}

def classify(points):
    points=sorted(points,key=lambda p:p['reported_rho_g_cm3'])
    if len(points)!=len(FACTORS):raise ValueError('FIVE_REAL_DENSITIES_REQUIRED')
    rho=[p['reported_rho_g_cm3'] for p in points]
    mass=[p['M_msun'] for p in points]
    if not all(rho[i]<rho[i+1] for i in range(len(rho)-1)):
        raise ValueError('CENTRAL_RHO_NOT_MONOTONIC')
    slopes=[(mass[i+1]-mass[i])/(rho[i+1]/rho[2]-rho[i]/rho[2]) for i in range(len(rho)-1)]
    centre=(mass[3]-mass[1])/(rho[3]/rho[2]-rho[1]/rho[2])
    wide=(mass[4]-mass[0])/(rho[4]/rho[2]-rho[0]/rho[2])
    good=all(s>0 for s in slopes)
    return {'interval_slopes_Msun_per_relative_rho':slopes,
        'central_slope_Msun_per_relative_rho':centre,
        'wide_slope_Msun_per_relative_rho':wide,
        'mass_strict_increasing':good,
        'mass_non_increasing_interval':any(s<=0 for s in slopes),
        'turning_point_within_five_samples':'UNRESOLVED_UNLESS_BRACKETED_BY_SIGN_CHANGE',
        'local_interpretation':'POSITIVE_LOCAL_FIXED_J_MASS_SLOPE_ONLY' if good
            else 'NEGATIVE_OR_MIXED_LOCAL_FIXED_J_SLOPE_REQUIRES_FOLLOWUP',
        'dynamical_stability':'NOT_DEMONSTRATED',
        'global_fixed_J_turning_point':'NOT_DEMONSTRATED'}

def solve_grid(evaluate,baseline,causal_upper,real_required=True):
    rho=float(baseline['rho_c_g_cm3'])
    j=float(baseline['J_cgs'])
    fc=float(baseline['commanded_f_hz'])
    if not rho*(1+max(FACTORS))<causal_upper:
        raise ValueError('F89_GRID_SAMPLES_REACH_OR_EXCEED_SOURCE_ACAUSAL_LIMIT')
    base=check_star(evaluate(math.log10(rho),fc),rho,real_required)
    if abs(base['M_msun']-baseline['M_msun'])>8e-5 or abs(base['J_cgs']/j-1)>BASE_J_REL_TOL:
        raise ValueError('F88_C_BASELINE_NOT_REPRODUCIBLE')
    if abs(base['spin_hz']-baseline['spin_hz'])>0.01:
        raise ValueError('F88_MEASURED_FREQUENCY_BASELINE_CHANGED')
    points=[]
    for frac in FACTORS:
        if frac==0:
            points.append({'requested_rho_g_cm3':rho,'reported_rho_g_cm3':base['rho_c_g_cm3'],
                'M_msun':base['M_msun'],'R_eq_km':base['R_equatorial_km'],
                'f_measured_hz':base['spin_hz'],'f_commanded_hz':fc,
                'J_measured_cgs':base['J_cgs'],'J_target_cgs':j,
                'J_relative_error':abs(base['J_cgs']/j-1),
                'direct_C_evaluations':1,'real_solver_checked':real_required,
                'evaluations':[{'baseline_replay':True,'M_msun':base['M_msun'],
                                'J_cgs':base['J_cgs']}],
                'fractional_rho_change':frac})
        else:
            p=root_at_fixed_j(evaluate,rho*(1+frac),fc,j,causal_upper,real_required)
            p['fractional_rho_change']=frac;points.append(p)
    result=classify(points)
    result['points']=points
    result['target_J_cgs']=j
    result['actual_C_evaluations_in_F89']=sum(p['direct_C_evaluations'] for p in points)
    return result

def main(args):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f81'))
    import f81_exact_mass_spin as F81
    f88=json.loads(Path(args.f88).read_text());audit=f88['audit']
    if audit['original_COMPOSE_APR_sha256']!=SOURCE_SHA:
        raise ValueError('F88_PINNED_PUBLISHER_SOURCE_MISMATCH')
    if audit['source_referenced_high_density_superluminal_nodes']!=24:
        raise ValueError('DO_NOT_HIDE_HIGH_DENSITY_ACAUSAL_SOURCE')
    if set(f88['actual_C_stars'])!=set(GRIDS):
        raise ValueError('REQUIRE_BOTH_ORIGINAL_F88_GRID_BASELINES')
    bins={'151x301':Path(args.rns151),'201x401':Path(args.rns201)}
    if {g:sha(bins[g]) for g in GRIDS}!=f88['binary_sha256']:
        raise ValueError('F88_ORIGINAL_BINARY_HASHES_MUST_REPRODUCE')
    if sha(Path(args.eos))!=audit['derived_F88_RNS_SHA256']:
        raise ValueError('F88_EXTENDED_EOS_HASH_CHANGED')
    report={'schema':'J0740_F89_DIRECT_C_RNS_LOCAL_FIXED_J_TURNING_POINT_SCREEN_V1',
        'model':audit['model'],'publisher_original_SHA256':SOURCE_SHA,
        'F88_source_C_binary_sha256':f88['binary_sha256'],
        'is_full_global_stability':'NO','mode_eigenfrequency_calculation':'NOT_RUN',
        'full_native_XPSI_photon_likelihood':'NOT_RUN',
        'original_publisher_global_causality':'FAIL_24_ACAUSAL_HIGH_DENSITY_NODES',
        'grid_results':{}}
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    for grid in GRIDS:
        binary=bins[grid]
        journal=out.parent/('F89_direct_C_'+grid+'.jsonl')
        journal.unlink(missing_ok=True)
        def observed(logrho,f,b=binary,log=journal):
            try:
                s=F81.evaluate_rns(b,Path(args.eos),logrho,f)
                rec={'logrho':logrho,'commanded_hz':f,'star':s}
            except Exception as exc:
                rec={'logrho':logrho,'commanded_hz':f,'error':repr(exc)}
                with log.open('a') as handle:handle.write(json.dumps(rec,allow_nan=False)+'\n')
                raise
            with log.open('a') as handle:handle.write(json.dumps(rec,allow_nan=False)+'\n')
            return s
        report['grid_results'][grid]=solve_grid(observed,f88['actual_C_stars'][grid],
               float(audit['grids'][grid]['causal_e_c_upper_g_cm3']))
        out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
        g=report['grid_results'][grid]
        print('F89_ACTUAL_C_FIXED_J_GRID',grid,
              {'local_slope':g['local_interpretation'],
               'central_slope':g['central_slope_Msun_per_relative_rho'],
               'C_evals':g['actual_C_evaluations_in_F89']},flush=True)
    good=all(report['grid_results'][g]['mass_strict_increasing'] for g in GRIDS)
    report['joint_numerical_interpretation']=('BOTH_GRIDS_POSITIVE_LOCAL_FIXED_J_MASS_SLOPE'
        if good else 'BOTH_GRIDS_NOT_CONFIRMED_POSITIVE_FIXED_J_SLOPE')
    report['axisymmetric_turning_point_statement']='ONLY_LOCAL_SAMPLED_SLOPES; no complete stable-branch or turning-point proof'
    report['dynamic_stability_statement']='NEEDS_EIGENMODE_CALCULATION; not implied by local dM/drho|J'
    out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print('F89_FINAL_LOCAL_FIXED_J_RESULT',report['joint_numerical_interpretation'],flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('f88','eos','rns151','rns201','out'):p.add_argument('--'+name,required=True)
    main(p.parse_args())
