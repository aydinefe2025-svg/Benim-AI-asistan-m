#!/usr/bin/env python3
"""F81: two independent, source-pinned C/RNS *reported* mass+spin roots.

Source EOS is the F80 original 1213-row BPS–MPA1 *surrogate* input. Neither
native MPA1 microphysics nor dynamically stable stars are certified here.
Only RNS C's existing printf diagnostics are modified to print high precision
and its already-calculated star.ang_mom, no equations or arrays are patched.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from scipy.optimize import brentq

EOS_SHA='f4a183661962acdddc7aebde3830116578feb6fba88a1a68c9fd57a993058675'
TOV_MODEL='JESTER_BPS_CRUST_LAL_MPA1_HIGH_PRESSURE_CROSSING_CAUSAL_TAIL_V1'
RNS_COMMIT='97e85d325a33e37f702306414533f6cd77812477'
TARGET_M=2.073
TARGET_F=346.536369
PHYSICAL_EOS_ACCEPTANCE='NOT_ESTABLISHED'
SOURCE_XPSI='NOT_RUN'
GRIDS=('151x301','201x401')
# F80's actual C roots used only as *starting seeds*, not as final calculated F81 stars.
SEEDS={'151x301':1.0230346639403752e15,'201x401':1.023278739033746e15}


def sha(path:Path)->str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def patch_print_only(original: str) -> str:
    old='printf("%g \\t %4.3f \\t %4.2f \\t %4.1f \\n",'
    new='printf("%.12e \\t %.12e \\t %.12e \\t %.12e \\t %.12e \\n",'
    old_args='star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI));'
    new_args='star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI), star.ang_mom);'
    if original.count(old)!=1 or original.count(old_args)!=1:
        raise ValueError('RNS_SOURCE_PRINT_DRIFT: refusing to modify any equation')
    return original.replace(old,new,1).replace(old_args,new_args,1)


def parse_rns(stdout:str)->dict:
    rows=[]
    for line in stdout.splitlines():
        parts=line.split()
        if len(parts)==4:
            try:
                if all(math.isfinite(float(s)) for s in parts):
                    raise ValueError('FIVE_C_COLUMNS_REQUIRED: actual J not emitted')
            except ValueError as e:
                if 'FIVE_C_COLUMNS_REQUIRED' in str(e): raise
            continue
        if len(parts)!=5: continue
        try:
            vals=[float(z) for z in parts]
        except ValueError: continue
        if not all(math.isfinite(v) for v in vals):raise ValueError('NONFINITE_REAL_C_OUTPUT')
        if vals[0]<=0 or vals[1]<=0 or vals[2]<=0 or vals[3]<=0 or vals[4]<=0:
            raise ValueError('NONPOSITIVE_REAL_C_STAR')
        rows.append(vals)
    if len(rows)!=1:raise ValueError('FIVE_C_COLUMNS_REQUIRED: unique RNS C diagnostics missing')
    rho15,mass,r_km,spin,J=rows[0]
    return {'rho_c_g_cm3':rho15*1e15,'M_msun':mass,'R_equatorial_km':r_km,
            'spin_hz':spin,'J_cgs':J,'central_energy_density_1e15_g_cm3':rho15}


def solve_grid(evaluate,seed_rho:float,target_m:float=TARGET_M,target_f:float=TARGET_F)->dict:
    """Nested, *bracketed* roots: M(log rho; f_command)=target, then f_report=target.

    The outer root adjusts RNS's *input* SetSpin command; only the actual
    output f=Omega/(2pi) qualifies, never the requested CLI -s value.
    """
    if not (1e13<seed_rho<1e17 and 0<target_m<4 and 1<target_f<2000):
        raise ValueError('INVALID_STAR_ROOT_PARAMETERS')
    trace=[]
    def checked(logrho:float,requested_f:float)->dict:
        star=evaluate(float(logrho),float(requested_f))
        for k in ('M_msun','spin_hz','R_equatorial_km','J_cgs','rho_c_g_cm3'):
            if k not in star or not math.isfinite(float(star[k])) or float(star[k])<=0:
                raise ValueError('INVALID_REAL_C_STAR_'+k)
        trace.append({'log10_rho':float(logrho),'f_command_hz':float(requested_f),
                      'M_msun':float(star['M_msun']),'f_reported_hz':float(star['spin_hz']),
                      'J_cgs':float(star['J_cgs'])})
        return star
    log_seed=math.log10(seed_rho)
    last={}
    def mass_root(requested_f:float)->dict:
        for half in (0.045,0.09,0.14):
            lo,hi=log_seed-half,log_seed+half
            left=checked(lo,requested_f)['M_msun']-target_m
            right=checked(hi,requested_f)['M_msun']-target_m
            if left*right<0: break
        else:raise ValueError('MASS_NOT_BRACKETED: no real C mass root at requested spin')
        def mres(x):return checked(x,requested_f)['M_msun']-target_m
        lr=brentq(mres,lo,hi,xtol=5e-9,rtol=1e-12,maxiter=20)
        star=checked(lr,requested_f)
        star=dict(star)
        star['commanded_f_hz']=float(requested_f)
        star['mass_error_msun']=float(star['M_msun']-target_m)
        star['spin_error_hz']=float(star['spin_hz']-target_f)
        last['star']=star
        return star

    # F80 gives a positive offset of ~0.08 Hz, but do not assume its sign.
    # Wide symmetric bracket protects against drift of SetSpin's internally
    # stopped root across grids.
    f_low=target_f-.3; f_high=target_f+.3
    first=mass_root(f_low)
    second=mass_root(f_high)
    if first['spin_error_hz']*second['spin_error_hz']>=0:
        raise ValueError('SPIN_NOT_BRACKETED: cannot trust requested -s as observed spin')
    froot=brentq(lambda f:mass_root(f)['spin_error_hz'],f_low,f_high,
                 xtol=0.0001,rtol=1e-12,maxiter=12)
    result=mass_root(froot)
    if abs(result['mass_error_msun'])>5e-6 or abs(result['spin_error_hz'])>0.005:
        raise ValueError('DUAL_MASS_SPIN_ROOT_NOT_ACCEPTED')
    if not (1e47<result['J_cgs']<1e51):
        raise ValueError('ANGULAR_MOMENTUM_NOT_PHYSICAL_RANGE')
    result['direct_C_evaluations']=len(trace)
    result['trace']=trace
    result['root_method']='nested_f_report_and_mass_brentq_on_actual_C_stars'
    result['status']='ACTUAL_DIRECT_C_TWO_CONSTRAINT_PASS_NOT_PHYSICAL_EOS_STABILITY'
    return result


def evaluate_rns(binary:Path, eos:Path, logrho:float, commanded_f:float)->dict:
    binary=Path(binary).resolve(); eos=Path(eos)
    if not binary.is_file() or not eos.is_file():raise ValueError('RNS_C_OR_ORIGINAL_EOS_NOT_PRESENT')
    if len(str(eos))>60:raise ValueError('RNS_C_CHAR80_EOS_PATH_TOO_LONG')
    # Real, exact pinned C executable (must not be confused with a synthetic test evaluator).
    cmd=[str(binary),'-f',str(eos),'-e',f'{10**logrho:.14e}','-s',f'{commanded_f:.9f}']
    p=subprocess.run(cmd,check=False,capture_output=True,text=True,timeout=120)
    if p.returncode!=0:raise RuntimeError('RNS_C_PROCESS_FAILED '+p.stdout[-700:]+p.stderr[-700:])
    try:r=parse_rns(p.stdout)
    except ValueError as err:raise RuntimeError('RNS_C_INVALID_OR_UNBRACKETED_MODEL: '+str(err)+' '+p.stdout[-700:]+p.stderr[-700:]) from err
    r['rho_input_g_cm3']=10**logrho
    r['real_C_solver']=True
    return r


def audit_pair(stars:dict,baseline:dict,source_sha:str,binary_sha:dict)->dict:
    if set(stars)!=set(GRIDS) or source_sha!=EOS_SHA or set(binary_sha)!=set(GRIDS):
        raise ValueError('SOURCE_OR_GRIDS_DRIFT')
    if binary_sha[GRIDS[0]]==binary_sha[GRIDS[1]]:raise ValueError('IDENTICAL_SOLVER_MESH_BINARIES')
    if baseline['model']!=TOV_MODEL or baseline['status']!='PASS_NUMERICAL_HYBRID_EOS_CANDIDATE_PHYSICAL_ACCEPTANCE_NOT_ESTABLISHED':
        raise ValueError('INCORRECT_STATIC_REFERENCE')
    rs=float(baseline['TOV']['M2p073']['R_km'])
    metrics={}
    for g,s in stars.items():
        if s.get('status')!='ACTUAL_DIRECT_C_TWO_CONSTRAINT_PASS_NOT_PHYSICAL_EOS_STABILITY':
            raise ValueError('REAL_C_STAR_STATUS_MISSING')
        if abs(s['M_msun']-TARGET_M)>5e-6 or abs(s['spin_hz']-TARGET_F)>.005 or s['J_cgs']<=0:
            raise ValueError('MEASURED_MASS_SPIN_J_NOT_ACCEPTED')
        metrics[g]={'mass_msun':s['M_msun'],'R_eq_km':s['R_equatorial_km'],
                    'f_report_hz':s['spin_hz'],'J_cgs':s['J_cgs'],
                    'I_derived_cgs':s['J_cgs']/(2*math.pi*s['spin_hz']),
                    'R_minus_static_m':(s['R_equatorial_km']-rs)*1000,
                    'central_g_cm3':s['rho_c_g_cm3'],
                    'f_command_hz':s['commanded_f_hz'],'C_evaluations':s['direct_C_evaluations']}
    a,b=GRIDS
    dr=abs(metrics[a]['R_eq_km']-metrics[b]['R_eq_km'])*1e3
    dj=abs(metrics[a]['J_cgs']/metrics[b]['J_cgs']-1)
    dm=abs(metrics[a]['mass_msun']-metrics[b]['mass_msun'])
    if dr>50 or dm>1e-5:raise ValueError('TWO_GRID_NUMERICAL_MISMATCH')
    return {'schema':'F81_BPS_MPA1_REAL_C_OUTPUT_TWO_CONSTRAINT_MASS_FREQ_J_V1',
            'status':'TWO_GRID_REAL_C_MASS_SPIN_J_NUMERICAL_PASS_NOT_PHYSICAL_EOS',
            'model':TOV_MODEL,'EOS_sha256':source_sha,'RNS_commit':RNS_COMMIT,
            'grids':metrics,'diff_R_eq_m':dr,'diff_M_msun':dm,
            'diff_J_fraction':dj,
            'not_original_nuclear_MPA1':True,
            'EOS_microphysical_acceptance':PHYSICAL_EOS_ACCEPTANCE,
            'global_fixed_J_stability':'NOT_RUN',
            'cold_BPS_to_core_Gibbs_phase_selection':'NOT_ESTABLISHED',
            'source_native_XPSI_photon_likelihood':SOURCE_XPSI,
            'seven_original_physical_EOS_Bayes':'NOT_RUN',
            'mesh_continuum_limit':'NOT_ESTABLISHED_TWO_SAMPLES_ONLY'}


def main():
    pa=argparse.ArgumentParser()
    pa.add_argument('--eos',type=Path,required=True)
    pa.add_argument('--rns151',type=Path,required=True)
    pa.add_argument('--rns201',type=Path,required=True)
    pa.add_argument('--tov',type=Path,required=True)
    pa.add_argument('--out',type=Path,required=True)
    z=pa.parse_args()
    if sha(z.eos)!=EOS_SHA:raise ValueError('EXACT_F80_EOS_SHA_MISMATCH')
    binaries={GRIDS[0]:z.rns151,GRIDS[1]:z.rns201}
    stars={}
    for g in GRIDS:
        binary=binaries[g]
        stars[g]=solve_grid(lambda lr,f,b=binary:evaluate_rns(b,z.eos,lr,f),SEEDS[g])
        print('F81 genuine C result',g,{k:stars[g][k] for k in ('M_msun','spin_hz','commanded_f_hz','J_cgs','R_equatorial_km','direct_C_evaluations')},flush=True)
    audited=audit_pair(stars,json.loads(z.tov.read_text()),sha(z.eos),{g:sha(binaries[g]) for g in GRIDS})
    out={'audit':audited,'actual_source_C_stars':stars,'source':{'EOS_sha256':sha(z.eos),
         'TOV_sha256':sha(z.tov),'binaries':{g:sha(binaries[g]) for g in GRIDS}},
         'revision':'F81 new observed-frequency matched roots, not F80 re-run'}
    z.out.parent.mkdir(parents=True,exist_ok=True)
    z.out.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print('F81 RESULT',json.dumps({k:audited[k] for k in ('status','diff_R_eq_m','diff_J_fraction','grids')},sort_keys=True))

if __name__=='__main__':main()
