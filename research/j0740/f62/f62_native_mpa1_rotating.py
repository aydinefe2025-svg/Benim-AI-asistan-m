"""F62: Original unmodified JESTER/LALSuite MPA1 at J0740 spin, direct RNS C roots.

This is a rotating GR *numerical source-model diagnostic*, NOT a physical EOS
admissibility certificate: the original JESTER NPZ contains a negative-cs2,
nonmonotone low-pressure source knot, and its n is an e/m_avg proxy. An RNS
interpolation that skips an invalid source knot does not heal the nuclear EOS.

Source-locked original JESTER MPA1 NPZ, F61 24 actual native LALSuite static TOV
roots, upstream RNS binary SHA and native exact table/resampling provenance.
Every reported star comes from a true RNS C subprocess at its stated density.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from scipy.optimize import brentq
import numpy as np

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent
sys.path.insert(0,str(PROJECT/'rotating_gr'))
from jester_to_rns import from_jester_npz, write_rns, C, G
from rns_benchmark import run_rns, sha256_file, OBSERVED_SPIN_HZ
from axis_ratio_rns import run_rns_at_spin_with_ratio_fallback

MPA1_NPZ_SHA='0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22'
F61_REPORT_SHA='7b2cbcf6df2dc55d33046d9af587dba179dcb2ec77bad0395e628742479cce0a'
JESTER_COMMIT='e6768650ce992abfd1153a6833857572fe5cd230'
RNS_COMMIT='97e85d325a33e37f702306414533f6cd77812477'
TARGETS=(2.073,2.175,2.200,2.250)
GRID_POINTS=(151,196)
M_TOL=.0015
HZ_TOL=.25
RNS_STATIC_DIFF_TOL_KM=.20
MESH_RADIUS_TOL_KM=.060
C2G=C*C/G*1e-3


def _sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def load_sources(npz, f61):
    if _sha(npz)!=MPA1_NPZ_SHA:raise ValueError('F62_MPA1_SOURCE_SHA_DRIFT')
    if _sha(f61)!=F61_REPORT_SHA:raise ValueError('F62_F61_STATIC_SOURCE_SHA_DRIFT')
    obj=json.loads(Path(f61).read_text())
    if (obj.get('status')!='DIRECT_NATIVE_STATIC_TOV_ONLY_NOT_ROTATING_OR_EOS_POSTERIOR'
            or obj.get('jester_source_commit')!=JESTER_COMMIT
            or obj.get('EOS_original_not_F42_modified') is not True
            or set(obj['results'])!={'APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2'}):
        raise ValueError('F62_F61_ORIGINAL_NATIVE_IDENTITY_DRIFT')
    if obj['results']['MPA1']['source_npz_sha256']!=MPA1_NPZ_SHA:
        raise ValueError('F62_MPA1_F61_CROSS_SHA_DRIFT')
    with np.load(npz,allow_pickle=False) as z:
        needed={'p','e','n','h','cs2','dloge_dlogp'}
        if not needed.issubset(z.files):raise ValueError('F62_ORIGINAL_MPA1_THERMO_MISSING')
        a={k:np.asarray(z[k],float) for k in needed}
    if len(a['p'])!=836 or not np.all(np.diff(a['p'])>0) or not np.isfinite(a['e']).all():
        raise ValueError('F62_ORIGINAL_MPA1_SOURCE_GRID_DRIFT')
    bad=int(np.count_nonzero(a['cs2']<=0))
    reversed=int(np.count_nonzero(np.diff(a['e'])<=0))
    if bad!=1 or reversed!=1:
        raise ValueError('F62_EXPECTED_MPA1_NATIVE_CRUST_PHYSICS_CHANGED_REAUDIT')
    for target in TARGETS:
        st=obj['results']['MPA1']['stars'][f'{target:.3f}']
        if st.get('status')!='DIRECT_NATIVE_LAL_TOV_WITH_SOURCE_MR_CROSSCHECK':
            raise ValueError('F62_F61_STATIC_TARGET_MISSING')
    return a,obj


def rho_from_F61_static(star, arr):
    pc=float(star['central_pressure_si_pa'])*G/C**4
    p=arr['p'];e=arr['e']
    if not p[0]<pc<p[-1]:raise ValueError('F62_MPA1_CENTRAL_PRESSURE_OUTSIDE_SOURCE')
    return float(np.exp(np.interp(math.log(pc),np.log(p),np.log(e)))*C2G)


def gate_star(model, target, spin):
    if not isinstance(model,dict):raise ValueError('F62_NO_DIRECT_C_MODEL')
    m=float(model['mass_msun']);r=float(model['radius_eq_km']);f=float(model['spin_hz_reported']);ec=float(model['central_energy_density_g_cm3'])
    if not all(map(math.isfinite,(m,r,f,ec))) or not (1.0<m<3 and 8<r<20 and ec>0):
        raise ValueError('F62_RNS_MODEL_OUTSIDE_PHYSICAL_NUMERICAL_BOUNDS')
    if abs(m-target)>M_TOL or abs(f-spin)>HZ_TOL:
        raise ValueError('F62_DIRECT_C_MASS_OR_SPIN_ROOT_RESIDUAL_FAIL')
    return True


def trial_root(binary, table, target, anchor_rho, spin, *, radius_cache=None):
    """Search a physical crossing of directly calculated RNS masses in central density.

    Ratio refinements are direct RNS C-model calls. The mass interpolation inside
    Brent is used only to locate next trial e_c; never reported as a star.
    """
    if not (1.5<target<2.6 and 2e14<anchor_rho<4e15 and 0<=spin<1000):
        raise ValueError('F62_INVALID_ROOT_SETTINGS')
    trace=[];cache={}
    def direct(ec):
        key=round(float(ec),2)
        if key in cache:return cache[key]
        if spin==0:
            s=run_rns(binary,table,central_density=float(ec),spin_hz=0.,spin_tolerance_hz=.10)
        else:
            s=run_rns_at_spin_with_ratio_fallback(binary,table,central_density=float(ec),spin_hz=spin)
        trace.append({'central_rho_g_cm3':float(ec),'mass_msun':float(s['mass_msun']),
             'radius_eq_km':float(s['radius_eq_km']),'frequency_hz_reported':float(s['spin_hz_reported']),
             'direct_C_solver_mode':s.get('solver_mode','RNS_C_SETSPIN'),'status':'DIRECT_C'})
        cache[key]=s
        return s
    # Derive a bracket from the independent, original LAL static source root;
    # never assume the same e_c is already at rotating target gravitational mass.
    trial_factors=(.76,.82,.87,.92,.96,1.00,1.04,1.09,1.15)
    candidates=[];failures=[]
    for factor in trial_factors:
        ec=anchor_rho*factor
        try:candidates.append(direct(ec))
        except (ValueError,RuntimeError,TimeoutError,OverflowError) as ex:
            failures.append({'ec':ec,'reason':type(ex).__name__+': '+str(ex)[:320]})
    ordered=sorted(candidates,key=lambda x:x['central_energy_density_g_cm3'])
    bracket=None
    for left,right in zip(ordered[:-1],ordered[1:]):
        if left['mass_msun']<target<right['mass_msun'] and right['mass_msun']>left['mass_msun']:
            bracket=(left,right);break
    if bracket is None:
        raise RuntimeError('F62_NO_DIRECT_RNS_BRACKET:'+str({'sampled':len(candidates),'failures':failures[:5],
                                'target':target,'masses':[round(x['mass_msun'],5) for x in ordered]}))
    l,r=bracket
    # For plateaued RNS rounded printed mass a direct trial root may already
    # pass; ensure the best direct model among all samples is preferred.
    def residual(ec):return direct(ec)['mass_msun']-target
    ec_root=brentq(residual,l['central_energy_density_g_cm3'],r['central_energy_density_g_cm3'],
                   xtol=1e-6,rtol=1e-9,maxiter=45)
    star=direct(ec_root)
    gate_star(star,target,spin)
    return {'status':'PASS_DIRECT_RNS_C_MASS_FREQUENCY_ROOT_NUMERICAL_ONLY',
            'star':{k:v for k,v in star.items() if k not in ('raw_stdout_tail','axis_ratio_bisection_trace')},
            'root_trace':trace,'trial_failures':failures,'static_anchor_rho_g_cm3':anchor_rho,
            'root_reported_mass_minus_target_msun':star['mass_msun']-target,
            'root_reported_frequency_minus_target_hz':star['spin_hz_reported']-spin,
            'actual_direct_C_calls':len(trace)}


def compare_results(d,ref):
    if set(d)!={str(x) for x in GRID_POINTS}:raise ValueError('F62_INVALID_MESH_SET')
    results={}
    for target in TARGETS:
        key=f'{target:.3f}'
        a,b=[d[str(n)]['targets'][key] for n in GRID_POINTS]
        radius_a=float(a['rotating']['star']['radius_eq_km'])
        radius_b=float(b['rotating']['star']['radius_eq_km'])
        for row in (a,b):
            gate_star(row['rotating']['star'],target,OBSERVED_SPIN_HZ)
            gate_star(row['static']['star'],target,0.)
            diff=row['static']['star']['radius_eq_km']-ref[key]['radius_km']
            if abs(diff)>RNS_STATIC_DIFF_TOL_KM:raise ValueError('F62_ORIGINAL_LAL_TOV_AND_RNS_STATIC_DISAGREE')
            if row['rotating']['star']['radius_eq_km']<=row['static']['star']['radius_eq_km']:
                raise ValueError('F62_ROTATING_RADIUS_NOT_EXPANDED')
        delta=radius_b-radius_a
        if abs(delta)>MESH_RADIUS_TOL_KM:
            raise ValueError('F62_EOS_TABLE_GRID_NOT_CONVERGED')
        results[key]={'target_mass_msun':target,'native_source_LAL_static_R_km':ref[key]['radius_km'],
                      'RNS_direct_151pt_rotation_req_km':radius_a,
                      'RNS_direct_196pt_rotation_req_km':radius_b,
                      'RNS_196pt_minus_151pt_eq_radius_km':delta,
                      'RNS_196pt_rotation_minus_static_km':radius_b-b['static']['star']['radius_eq_km'],
                      'RNS_196pt_static_minus_native_LAL_km':b['static']['star']['radius_eq_km']-ref[key]['radius_km'],
                      'source_original_EOS_global_physical_certification':'FAIL_ORIGINAL_LOW_PRESSURE_NEGATIVE_CS2_KNOT',
                      'exact_photon_level_XPSI_Bayes':'NOT_RUN',
                      'global_constant_J_stability':'NOT_RUN'}
    return results


def run(source_npz,f61,binary,out,*,mesh_points=GRID_POINTS):
    arr,refobj=load_sources(source_npz,f61)
    if tuple(mesh_points)!=GRID_POINTS:raise ValueError('F62_MUST_COMPARE_BOTH_PINNED_MESHES')
    ref=refobj['results']['MPA1']['stars']
    original_bad_indices=np.flatnonzero(arr['cs2']<=0).tolist()
    report={'schema':'J0740_F62_ORIGINAL_MPA1_SOURCE_DERIVED_RNS_C_ROTATING_GR_V1',
        'status':'IN_PROGRESS_NOT_YET_PHYSICALLY_CERTIFIED',
        'original_JESTER_source_MPA1_npz_SHA256':_sha(source_npz),
        'F61_LAL_7EOS_static_reference_sha256':_sha(f61),
        'pinned_RNS_commit':RNS_COMMIT,'RNS_compiled_executable_sha256':sha256_file(binary),
        'f_hz':OBSERVED_SPIN_HZ,'target_masses_msun':TARGETS,
        'original_MPA1_unmodified_source_knots_count':len(arr['p']),
        'original_MPA1_negative_cs2_source_indices':original_bad_indices,
        'original_MPA1_raw_energy_nonincreasing_edges':int(np.count_nonzero(np.diff(arr['e'])<=0)),
        'low_pressure_source_defect_preserved_in_provenance_not_certified':True,
        'source_EOS_physical_acceptance':'NOT_ESTABLISHED_LOWPRESSURE_NEGATIVE_DERIVATIVE',
        'mass_frequency_source_root_type':'TRUE_RNS_C_EVALUATION_NOT_INTERPOLATED_MODEL',
        'posterior':'NOT_RUN','native_photon_XPSI':'NOT_RUN','fixed_J_stability':'NOT_RUN',
        'mesh_runs':{},'verified_rotating_static_mesh_comparisons':{},
        'limitations':[
           'Original JESTER source was only log-resampled for RNS; the source low pressure negative cs2 and energy reversal could be skipped by resampling and remain unphysical',
           'Source n is e/m_avg proxy, not first-law physical baryon density; gravitational M/R convergence cannot validate M0, stability, or EOS global physical admission',
           'Rotating GR root is direct full-RNS C but not constant-J global stability certification',
           'F61 static TOV root source is original LAL, not F42 lifted barotrope',
           'No XPSI source-native photon likelihood or physical seven-original-EOS Bayes',
           'Mass prior support coverage cannot be directly assigned to observational EOS weights without full physical admissibility and likelihood',
        ]}
    target=Path(out);target.parent.mkdir(parents=True,exist_ok=True)
    def save():target.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    save()
    for n in GRID_POINTS:
        rows,conversion=from_jester_npz(source_npz,points=n)
        table=target.parent/f'MPA1_ORIGINAL_JESTER_source_logresampled_{n}pt.rns'
        write_rns(table,rows)
        report['mesh_runs'][str(n)]={'RNS_source_table_sha256':sha256_file(table),
            'EOS_source_name':'MPA1','source_converted_not_F42_lift':True,
            'source_original_bad_low_pressure_knot_NOT_REPAIRED':True,
            'source_conversion':conversion,'targets':{}}
        save()
        for mass in TARGETS:
            key=f'{mass:.3f}'
            static=ref[key];rho=rho_from_F61_static(static,arr)
            record={'status':'IN_PROGRESS','F61_direct_native_static_TOV_star':static,
                    'F61_static_seed_energy_density_g_cm3':rho}
            report['mesh_runs'][str(n)]['targets'][key]=record;save()
            try:
                record['rotating']=trial_root(binary,table,mass,rho,OBSERVED_SPIN_HZ)
                record['static']=trial_root(binary,table,mass,rho,0.)
                record['status']='PASS_DIRECT_ROTATING_AND_STATIC_RNS_C_DIAGNOSTIC'
            except Exception as exc:
                record['status']='FAIL_DIRECT_RNS_DIAGNOSTIC_NOT_PHYSICS_CLAIM'
                record['failure_type']=type(exc).__name__
                record['failure_reason']=str(exc)[:1600]
            save()
            print('F62',n,'mesh',key,'Msun',record['status'],flush=True)
            if record['status'].startswith('FAIL'):
                raise RuntimeError(record['failure_reason'])
    report['verified_rotating_static_mesh_comparisons']=compare_results(report['mesh_runs'],ref)
    report['status']='DIRECT_SOURCE_DERIVED_MPA1_RNS_ROTATING_4_MASSES_TWO_MESHES_PASS_NOT_PHYSICAL_EOS_BAYES'
    save()
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--f61',type=Path,required=True)
    p.add_argument('--rns',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    x=p.parse_args()
    r=run(x.source,x.f61,x.rns,x.out)
    print(json.dumps({'status':r['status'],'targets':list(r['verified_rotating_static_mesh_comparisons'])},sort_keys=True))

if __name__=='__main__':main()