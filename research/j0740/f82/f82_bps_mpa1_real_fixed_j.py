#!/usr/bin/env python3
"""F82 real direct-C constant angular momentum density curve for the *F81 surrogate*.

Uses archived 201x401 C J as an exact reference for *both* real spacetime meshes.
Numerical sampled fixed-J turning point is NOT dynamical or Gibbs-phase stability.
No new EOS, no photon likelihood, no new microphysical validation.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
SCIENCE=HERE.parent
EOS_SHA='f4a183661962acdddc7aebde3830116578feb6fba88a1a68c9fd57a993058675'
RNS_COMMIT='97e85d325a33e37f702306414533f6cd77812477'

F81_RESULT_SHA='36d726706f8aadcbae416693dc4f682c890defe9ca896b76641655140aede620'
F81_SCHEMA='F81_BPS_MPA1_REAL_C_OUTPUT_TWO_CONSTRAINT_MASS_FREQ_J_V1'
J_REFERENCE=6.065849263583e48
ANCHOR_RHO=1.023284986094e15
# Fixed predeclared initial sweep, includes the F81 anchor and follows both sides
# of a putative turning point. NOT a guaranteed entire neutron-star branch.
DENSITY_E15=(0.85,0.95,1.023284986094,1.15,1.3,1.45,1.6,1.75,1.9,2.05,2.17,2.29,2.42,2.48)
GRIDS=('151x301','201x401')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate_source(f81_path,eos,binaries):
    if sha(eos)!=EOS_SHA or sha(f81_path)!=F81_RESULT_SHA:
        raise ValueError('F82_ARCHIVED_F81_OR_EOS_BYTES_DRIFT')
    v=json.loads(Path(f81_path).read_text())
    if (v['audit']['schema']!=F81_SCHEMA or v['audit']['status']!='TWO_GRID_REAL_C_MASS_SPIN_J_NUMERICAL_PASS_NOT_PHYSICAL_EOS'
            or v['audit']['global_fixed_J_stability']!='NOT_RUN' or v['audit']['EOS_microphysical_acceptance']!='NOT_ESTABLISHED'
            or v['audit']['EOS_sha256']!=EOS_SHA):
        raise ValueError('F82_ARCHIVED_F81_PHYSICS_STATUS_DRIFT')
    a=v['actual_source_C_stars']['201x401']
    if not (abs(a['J_cgs']/J_REFERENCE-1)<1e-12 and abs(a['spin_hz']-346.536369)<.005
            and abs(a['M_msun']-2.073)<5e-6):
        raise ValueError('F82_F81_ACTUAL_C_J_ANCHOR_DRIFT')
    if set(binaries)!=set(GRIDS) or not all(Path(p).is_file() for p in binaries.values()):
        raise ValueError('F82_TWO_REAL_C_SOLVERS_REQUIRED')
    digest={g:sha(p) for g,p in binaries.items()}
    if digest[GRIDS[0]]==digest[GRIDS[1]]:raise ValueError('F82_TWO_DIFFERENT_GR_SPATIAL_SOLVER_HASHES_REQUIRED')
    return v,digest

def peak_summary(stars,*,min_success=9):
    a=sorted((s for s in stars if s.get('status')=='DIRECT_C_FIXED_J_NUMERICAL_PASS_NOT_STABILITY_CERTIFICATE'),
             key=lambda x:x['ec_g_cm3'])
    if len(a)<min_success:
        return {'status':'INSUFFICIENT_REAL_C_CONSTANT_J_STARS','count':len(a),'dynamic_stability':'NOT_ESTABLISHED'}
    index=max(range(len(a)),key=lambda i:a[i]['mass_msun'])
    local=index>0 and index<len(a)-1 and a[index-1]['mass_msun']<a[index]['mass_msun'] and a[index+1]['mass_msun']<a[index]['mass_msun']
    return {'status':'SAMPLED_LOCAL_CONSTANT_J_MASS_MAX_BRACKETED_NOT_DYNAMIC_STABILITY' if local else 'NO_SAMPLED_CONSTANT_J_TURNOVER',
            'count':len(a),'peak_density_g_cm3':a[index]['ec_g_cm3'],
            'peak_M_msun':a[index]['mass_msun'],
            'peak_radius_eq_km':a[index]['radius_eq_km'],
            'peak_spin_hz':a[index]['spin_hz'],
            'peak_axis_ratio':a[index]['axis_ratio'],
            'neighbors': [{'ec_g_cm3':a[k]['ec_g_cm3'],'M_msun':a[k]['mass_msun']} for k in range(max(0,index-1),min(len(a),index+2))],
            'global_dynamic_stability':'NOT_ESTABLISHED','physical_original_MPA1':'NOT_ESTABLISHED'}

def compare_grids(coarse,fine):
    m={x['ec_g_cm3']:x for x in coarse if x.get('status')=='DIRECT_C_FIXED_J_NUMERICAL_PASS_NOT_STABILITY_CERTIFICATE'}
    out=[]
    for y in fine:
        if y.get('status')!='DIRECT_C_FIXED_J_NUMERICAL_PASS_NOT_STABILITY_CERTIFICATE':continue
        v=m.get(y['ec_g_cm3'])
        if not v:continue
        if (abs(y['relative_J_residual'])>1e-5 or abs(v['relative_J_residual'])>1e-5):
            raise ValueError('F82_J_CONSTRAINT_MISMATCH')
        out.append({'ec_g_cm3':y['ec_g_cm3'],'delta_M_msun':y['mass_msun']-v['mass_msun'],
                    'delta_R_m':1000*(y['radius_eq_km']-v['radius_eq_km']),
                    'relative_J_error_fine':y['relative_J_residual'],
                    'relative_J_error_coarse':v['relative_J_residual']})
    return {'pairs':out,'count':len(out),
            'max_abs_mass_msun':max((abs(x['delta_M_msun']) for x in out),default=None),
            'max_abs_radius_m':max((abs(x['delta_R_m']) for x in out),default=None)}

def run(eos:Path,f81:Path,binaries:dict,out:Path,density_e15=DENSITY_E15):
    # Deferred import keeps pure acceptance tests runnable without vendor C/RNS.
    sys.path.insert(0,str(SCIENCE/'f63'))
    from f63_original_mpa1_fixed_J import fixed_j_at_density, c_call
    a,binhash=validate_source(f81,eos,binaries)
    report={'schema':'F82_BPS_MPA1_SURROGATE_REAL_C_FIXED_J_SAMPLED_TWO_SPATIAL_GRIDS_V1',
            'status':'IN_PROGRESS','original_RNS_commit':RNS_COMMIT,
            'source_EOS_sha256':sha(eos),'source_F81_JSON_sha256':sha(f81),
            'source_real_RNS_binary_SHA256':binhash,'J_fixed_cgs':J_REFERENCE,
            'anchor_F81_201':{k:a['actual_source_C_stars']['201x401'][k] for k in ('rho_c_g_cm3','M_msun','J_cgs','spin_hz','R_equatorial_km')},
            'input_density_e15_predeclared':list(density_e15),'coarse_stars':[], 'fine_spatial_star_pairs':[],
            'failures':[],'original_MPA1_microphysics':'NOT_ESTABLISHED',
            'BPS_core_Gibbs_phase_thermodynamics':'NOT_ESTABLISHED',
            'sampled_turning_not_dynamical_stability':True,
            'source_native_XPSI_photons':'NOT_RUN','seven_physical_EOS_Bayes':'NOT_RUN'}
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    def save():out.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    def fixed_one(grid,ec,seed,stage):
        try:
            # F63's already-tested *real C* constant-J root, identical algorithm,
            # but here the EOS and target J are explicitly the separate F81 surrogate.
            x=fixed_j_at_density(lambda density,r:c_call(binaries[grid],eos,density,ratio=r),ec,J_REFERENCE,seed=seed)
            x['grid']=grid;x['stage']=stage
            if x['direct_C_evaluations']<2 or abs(x['relative_J_residual'])>1e-5:
                raise ValueError('F82_NOT_ACTUAL_C_J_ROOT')
            print('F82',grid,'ec_E15',round(ec/1e15,9),'M',x['mass_msun'],'Jerr',x['relative_J_residual'],'R',x['radius_eq_km'],'ncall',x['direct_C_evaluations'],flush=True)
            return x
        except (ValueError,RuntimeError,OverflowError) as e:
            y={'ec_g_cm3':ec,'grid':grid,'stage':stage,'status':'REJECTED_REAL_C_ROOT','error':str(e)[:250]}
            report['failures'].append(y)
            print('F82 REAL C FAILED',y,flush=True)
            return y
    seed=.976
    for x in density_e15:
        ec=float(x)*1e15; v=fixed_one(GRIDS[0],ec,seed,'coarse')
        report['coarse_stars'].append(v)
        if v['status'].startswith('DIRECT_C_'):seed=v['axis_ratio']
        save()
    report['coarse_peak']=peak_summary(report['coarse_stars'],min_success=10);save()
    if not report['coarse_peak']['status'].startswith('SAMPLED_'):
        report['status']='FAILED_TO_BRACKET_REAL_C_FIXED_J_COARSE_TURNOVER';save();return report
    # Focus grid comparison on pre-registered continuum of exactly matched density
    # points around real coarse maximum. Two grids solve SAME target J at SAME ec.
    near=report['coarse_peak']['neighbors']
    lo=near[0]['ec_g_cm3'];hi=near[-1]['ec_g_cm3']
    densities=[float(v) for v in np.linspace(lo,hi,7)]
    report['matched_peak_density_g_cm3']=densities
    near_seed=report['coarse_peak']['peak_axis_ratio']
    for ec in densities:
        pair={}
        for g in GRIDS:
            pair[g]=fixed_one(g,ec,near_seed,'matched-peak-two-grid')
        report['fine_spatial_star_pairs'].append(pair)
        if pair[GRIDS[1]]['status'].startswith('DIRECT_C_'):
            near_seed=pair[GRIDS[1]]['axis_ratio']
        save()
    c=[p[GRIDS[0]] for p in report['fine_spatial_star_pairs']]
    f=[p[GRIDS[1]] for p in report['fine_spatial_star_pairs']]
    report['matched_coarse_peak']=peak_summary(c,min_success=5)
    report['matched_fine_peak']=peak_summary(f,min_success=5)
    report['mesh_comparison']=compare_grids(c,f)
    good=(report['matched_coarse_peak']['status'].startswith('SAMPLED_')
          and report['matched_fine_peak']['status'].startswith('SAMPLED_')
          and report['mesh_comparison']['count']>=5
          and report['mesh_comparison']['max_abs_mass_msun']<.008
          and report['mesh_comparison']['max_abs_radius_m']<110)
    report['anchor_density_below_sampled_peak']=ANCHOR_RHO<report['matched_fine_peak'].get('peak_density_g_cm3',0)
    report['status']='REAL_C_TWO_MESH_SAMPLED_FIXED_J_TURNOVER_ACCEPTED_NOT_DYNAMIC_STABILITY' if good else 'REAL_C_FIXED_J_TURNING_OR_MESH_CONVERGENCE_NOT_ACCEPTED'
    save()
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--eos',type=Path,required=True);p.add_argument('--f81',type=Path,required=True)
    p.add_argument('--rns151',type=Path,required=True);p.add_argument('--rns201',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    d=run(args.eos,args.f81,{'151x301':args.rns151,'201x401':args.rns201},args.out)
    print('F82_RESULT',json.dumps({k:d.get(k) for k in ('status','coarse_peak','matched_fine_peak','mesh_comparison','anchor_density_below_sampled_peak')},sort_keys=True),flush=True)
    if not d['status'].startswith('REAL_C_TWO_MESH_'):raise SystemExit('F82_REAL_FIXED_J_ADMISSION_FAILED; raw failed attempts preserved')
if __name__=='__main__':main()
