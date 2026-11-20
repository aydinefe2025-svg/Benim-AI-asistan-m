#!/usr/bin/env python3
"""Native C/RNS rotating 346.536369-Hz 2.073-Msun star for separately defined
CompOSE APR(APR) unified cold EOS + explicitly appended analytic surface extension.
This is NOT source APR4_EPP, F83 BPS-MPA1, global EOS physical certification,
X-PSI photon likelihood, or dynamic stability.
"""
import argparse,hashlib,math,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f81'))
import f81_exact_mass_spin as F81
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f87'))
from f87_real_tov_from_compose import EOS,ONE_MEVFM3,C

GRIDS=('151x301','201x401')
SEEDS={'151x301':1.72e15,'201x401':1.72e15}
EXPECTED_SOURCE_ZIP='8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12'
TARGET_M=2.073;TARGET_F=346.536369



def solve_grid_bounded(evaluate, seed_rho: float):
    """Root measured C mass and spin with a tolerance-aware bracketed outer solve.

    The measured 0.005-Hz acceptance criterion is never relaxed. Avoid a
    1e-4-Hz Brent convergence requirement (and a 12-iteration cap) that is
    stricter than the actual physical acceptance gate.
    """
    from scipy.optimize import brentq
    if not (1e13 < seed_rho < 1e17):
        raise ValueError('INVALID_REAL_C_SEED')
    trace = []

    def checked(logrho, requested_f):
        star = evaluate(float(logrho), float(requested_f))
        for key in ('M_msun','spin_hz','R_equatorial_km','J_cgs','rho_c_g_cm3'):
            if key not in star or not math.isfinite(float(star[key])) or star[key] <= 0:
                raise ValueError('INVALID_REAL_C_STAR_'+key)
        trace.append({'log10_rho':float(logrho),'f_command_hz':float(requested_f),
                      'M_msun':float(star['M_msun']),
                      'f_reported_hz':float(star['spin_hz']),
                      'J_cgs':float(star['J_cgs'])})
        return star

    def mass_root(requested_f):
        seed = math.log10(seed_rho)
        bracket = None
        for half in (.045, .09, .14):
            left, right = seed-half, seed+half
            delta_l=checked(left,requested_f)['M_msun']-TARGET_M
            delta_r=checked(right,requested_f)['M_msun']-TARGET_M
            if delta_l*delta_r < 0:
                bracket=(left,right)
                break
        if bracket is None:
            raise ValueError('MASS_NOT_BRACKETED_IN_REAL_C')
        lr=brentq(lambda x:checked(x,requested_f)['M_msun']-TARGET_M,
                  *bracket,xtol=5e-9,rtol=1e-12,maxiter=30)
        star=dict(checked(lr,requested_f))
        star['commanded_f_hz']=float(requested_f)
        star['mass_error_msun']=float(star['M_msun']-TARGET_M)
        star['spin_error_hz']=float(star['spin_hz']-TARGET_F)
        return star

    lo,hi=TARGET_F-.3,TARGET_F+.3
    left=mass_root(lo)
    right=mass_root(hi)
    if left['spin_error_hz']*right['spin_error_hz'] >= 0:
        raise ValueError('SPIN_NOT_BRACKETED_BY_MEASURED_C_OUTPUT')
    best=min((left,right), key=lambda s: abs(s['spin_error_hz']))
    for _ in range(32):
        if abs(best['spin_error_hz']) <= .005 and abs(best['mass_error_msun']) <= 5e-6:
            break
        mid=(lo+hi)/2
        star=mass_root(mid)
        if abs(star['spin_error_hz'])<abs(best['spin_error_hz']):
            best=star
        if left['spin_error_hz']*star['spin_error_hz'] <= 0:
            hi=mid
            right=star
        else:
            lo=mid
            left=star
    else:
        raise ValueError('MEASURED_C_SPIN_NOT_WITHIN_0p005_HZ_AFTER_32_BISECTIONS')
    if abs(best['mass_error_msun'])>5e-6 or abs(best['spin_error_hz'])>.005:
        raise ValueError('REAL_C_MASS_SPIN_TOLERANCE_NOT_REACHED')
    if not (1e47<best['J_cgs']<1e51):
        raise ValueError('REAL_C_ANGULAR_MOMENTUM_RANGE_FAIL')
    best['direct_C_evaluations']=len(trace)
    best['trace']=trace
    best['root_method']='measured_C_mass_brentq_spin_bisection_tolerance_aware'
    best['status']='ACTUAL_DIRECT_C_TWO_CONSTRAINT_PASS_NOT_PHYSICAL_EOS_STABILITY'
    return best

def verify(stars,bins,source_data,rns_source,eos_file,static):
    if set(stars)!=set(GRIDS) or set(bins)!=set(GRIDS):raise ValueError('TWO_INDEPENDENT_GRIDS_REQUIRED')
    if bins[GRIDS[0]]==bins[GRIDS[1]]:raise ValueError('TWO_RNS_BINARY_SHA_IDENTICAL')
    if source_data['original_APR_compose_sha256']!=EXPECTED_SOURCE_ZIP:
        raise ValueError('WRONG_REAL_COMPOSE_PUBLISHER_SOURCE')
    if source_data['rns_input_file_sha256']!=F81.sha(eos_file):raise ValueError('RNS_SOURCE_EOS_MUTATED')
    if source_data['original_source_nodes_cs2_gt1']!=24 or source_data['analytical_extension_rows']!=100:
        raise ValueError('DO_NOT_HIDE_SOURCE_CAUSALITY_OR_SURFACE_EXTENSION')
    if abs(static['target_M2p073_static']['M_Msun']-TARGET_M)>1e-6:raise ValueError('PUBLISHED_TOV_NOT_MATCHED')
    native_E_super=float(rns_source.E[next(i for i in range(len(rns_source.nb)) if rns_source.cs_source[i]>1)])
    max_source_rho=native_E_super*ONE_MEVFM3/C**2
    out={}
    for name in GRIDS:
        v=stars[name]
        if v.get('status')!='ACTUAL_DIRECT_C_TWO_CONSTRAINT_PASS_NOT_PHYSICAL_EOS_STABILITY':raise ValueError('NOT_REAL_C_GR_EINSTEIN_ROOT')
        if abs(v['M_msun']-TARGET_M)>5e-6 or abs(v['spin_hz']-TARGET_F)>.005:raise ValueError('REAL_C_MASS_SPIN_OUTSIDE_TOLERANCE')
        if not (1e47<v['J_cgs']<1e51 and 1e15<v['rho_c_g_cm3']<max_source_rho):raise ValueError('REAL_C_J_OR_CAUSAL_CENTRE_FAIL')
        if not (v['direct_C_evaluations']>=5 and len(v['trace'])==v['direct_C_evaluations']):raise ValueError('REAL_C_TRACE_INCOMPLETE')
        out[name]={'M_msun':v['M_msun'],'f_report_Hz':v['spin_hz'],'R_eq_km':v['R_equatorial_km'],'J_cgs':v['J_cgs'],'rho_c_g_cm3':v['rho_c_g_cm3'],'causal_e_c_upper_g_cm3':max_source_rho,'actual_C_evaluations':v['direct_C_evaluations'],'Rminus_static_m':(v['R_equatorial_km']-static['target_M2p073_static']['R_km'])*1000}
    a,b=(out[g] for g in GRIDS)
    if abs(a['R_eq_km']-b['R_eq_km'])>.08:raise ValueError('RNS_SPATIAL_MESH_R_GT_80M')
    return {'status':'TWO_REAL_INDEPENDENT_C_RNS_GR_ROOTS_NUMERICALLY_MATCHED_NOT_GLOBAL_EOS_CERTIFICATION',
      'schema':'J0740_F88_SOURCE_APR_UNIFIED_LOW_DENSITY_EXPLICIT_EXTENSION_REAL_ROTATING_GR_V1','model':'CompOSE_APR_APR_UNIFIED_PLUS_EXPLICIT_ANALYTIC_LOW_DENSITY_EXTENSION_NOT_APR4EPP',
      'grids':out,'R_eq_grid_difference_m':abs(a['R_eq_km']-b['R_eq_km'])*1000,
      'original_COMPOSE_APR_sha256':EXPECTED_SOURCE_ZIP,'derived_F88_RNS_SHA256':F81.sha(eos_file),
      'source_referenced_high_density_superluminal_nodes':24,'normal_equation_C_star_stability':'NOT_ESTABLISHED',
      'original_Salmi_XPSI_10817_likelihood_calls':'PREVIOUSLY_RUN_NOT_REPEATED',
      'current_native_photon_calls':0,'XPSI_full_MR_EOS_Bayes':'NOT_RUN'}

def run(source_dir,eos,eosmeta,rns151,rns201,static,out):
    model=EOS(source_dir);sd=json.loads(Path(eosmeta).read_text());tov=json.loads(Path(static).read_text())
    bins={k:F81.sha(v) for k,v in zip(GRIDS,[rns151,rns201])}
    stars={}
    for g,binary in zip(GRIDS,[rns151,rns201]):
        # Write every direct physical C evaluation immediately: failures must retain traces.
        journal=Path(out).parent/('F88_live_C_trace_'+g+'.jsonl')
        journal.parent.mkdir(parents=True,exist_ok=True)
        journal.unlink(missing_ok=True)
        def observed(lr,f,b=binary,log=journal):
            try:
                star=F81.evaluate_rns(b,eos,lr,f)
                rec={'log10_rho':lr,'commanded_spin_Hz':f,'actual_C_star':star}
            except Exception as error:
                rec={'log10_rho':lr,'commanded_spin_Hz':f,'C_error':repr(error)}
                with log.open('a') as handle: handle.write(json.dumps(rec,allow_nan=False)+'\n')
                raise
            with log.open('a') as handle: handle.write(json.dumps(rec,allow_nan=False)+'\n')
            return star
        stars[g]=solve_grid_bounded(observed,SEEDS[g])
        print('ACTUAL_COMPOSE_UNIFIED_C_RNS',g,{k:stars[g][k] for k in ('M_msun','spin_hz','R_equatorial_km','J_cgs','rho_c_g_cm3','direct_C_evaluations')},flush=True)
    audit=verify(stars,bins,sd,model,eos,tov)
    obj={'audit':audit,'actual_C_stars':stars,'binary_sha256':bins,'source':sd,'source_static_sha256':F81.sha(static)}
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n');return obj

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--eos',required=True);p.add_argument('--eosmeta',required=True);p.add_argument('--rns151',required=True);p.add_argument('--rns201',required=True);p.add_argument('--static',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    run(a.source,Path(a.eos),a.eosmeta,Path(a.rns151),Path(a.rns201),a.static,a.out)
