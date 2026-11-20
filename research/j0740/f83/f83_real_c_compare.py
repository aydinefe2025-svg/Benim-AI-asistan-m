#!/usr/bin/env python3
"""Two-grid genuine C/RNS comparison of a *new* F83 piecewise-cold EOS.

This reuses F81's actual code path for reported mass/frequency roots, never
transfers F81 stars to the new source table. This is numerical sensitivity,
NOT a microphysical EOS or fixed-J stability certification.
"""
from __future__ import annotations
import argparse,sys,json,math,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f81'))
import f81_exact_mass_spin as F81
sys.path.insert(0,str(Path(__file__).resolve().parent))
import f83_cold_integrability as F83

SCHEMA='F83_BPS_MPA1_PIECEWISE_COLD_REAL_C_TWO_SPATIAL_GRIDS_SENSITIVITY_V1'

def compare_new_old(new,old,expected_sha,srcsha):
    if srcsha != F83.EOS_SHA or len(expected_sha)!=64:
        raise ValueError('F83_REBUILT_MODEL_SOURCE_DRIFT')
    if set(new)!=set(F81.GRIDS) or set(old)!=set(F81.GRIDS):
        raise ValueError('F83_TWO_GRIDS_REQUIRED')
    out={}
    for g in F81.GRIDS:
        a=new[g];b=old[g]
        if a['status']!='ACTUAL_DIRECT_C_TWO_CONSTRAINT_PASS_NOT_PHYSICAL_EOS_STABILITY':
            raise ValueError('F83_NEW_STAR_NOT_GENUINE_C')
        if abs(a['M_msun']-F81.TARGET_M)>5e-6 or abs(a['spin_hz']-F81.TARGET_F)>.005:
            raise ValueError('F83_NEW_C_MASS_OR_SPIN_NOT_TARGET')
        if not (a['direct_C_evaluations']>=5 and 1e47<a['J_cgs']<1e51 and len(a['trace'])>=5):
            raise ValueError('F83_NO_TRUE_C_CALL_TRACE_OR_J')
        out[g]={'new_M_msun':a['M_msun'],'new_frequency_hz':a['spin_hz'],
            'new_R_eq_km':a['R_equatorial_km'],'new_J_cgs':a['J_cgs'],
            'old_R_eq_km':b['R_equatorial_km'],'old_J_cgs':b['J_cgs'],
            'new_minus_old_R_m':1000*(a['R_equatorial_km']-b['R_equatorial_km']),
            'new_over_old_J_minus_1':a['J_cgs']/b['J_cgs']-1,
            'real_new_C_evaluations':a['direct_C_evaluations']}
    if abs(out[F81.GRIDS[0]]['new_R_eq_km']-out[F81.GRIDS[1]]['new_R_eq_km'])>0.05:
        raise ValueError('F83_NEW_EOS_TWO_GRID_GEOMETRIC_FAILURE')
    return {'schema':SCHEMA,'status':'NEW_PIECEWISE_INTEGRABLE_SOURCE_REAL_TWO_GRID_C_NUMERICAL_PASS',
        'old_original_F80_F81_EOS_sha256':srcsha,'new_F83_EOS_sha256':expected_sha,
        'model':'F83_EXPLICIT_PIECEWISE_LINEAR_EPSILON_OF_P_AND_ANALYTIC_ENTHALPY_ALTERNATIVE',
        'grids':out,
        'Gibbs_BPS_core_phase_thermodynamics':'NOT_ESTABLISHED',
        'global_fixed_J_and_dynamic_mode_stability':'NOT_ESTABLISHED_FOR_NEW_EOS',
        'XPSI_full_native_photon_likelihood':'NOT_RUN',
        'seven_original_EOS_Bayes':'NOT_RUN'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--new-eos',type=Path,required=True)
    p.add_argument('--f81',type=Path,required=True);p.add_argument('--rns151',type=Path,required=True)
    p.add_argument('--rns201',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    z=p.parse_args()
    digest=F83.sha(z.new_eos)
    if digest==F83.EOS_SHA:raise ValueError('F83_NOT_ACTUALLY_NEW_SOURCE')
    old=json.loads(z.f81.read_text())['actual_source_C_stars']
    stars={}
    for g,binary in zip(F81.GRIDS,[z.rns151,z.rns201]):
        def ev(lr,f):return F81.evaluate_rns(binary,z.new_eos,lr,f)
        star=F81.solve_grid(ev,F81.SEEDS[g]);stars[g]=star
        print('F83 real new C',g,star['M_msun'],star['spin_hz'],star['R_equatorial_km'],star['J_cgs'],star['direct_C_evaluations'],flush=True)
    audit=compare_new_old(stars,old,digest,F83.EOS_SHA)
    obj={'audit':audit,'new_actual_real_C_stars':stars,
         'solver_binary_sha256':{k:F81.sha(v) for k,v in zip(F81.GRIDS,[z.rns151,z.rns201])}}
    if len(set(obj['solver_binary_sha256'].values()))!=2:raise ValueError('F83_TWO_BINARY_MESH_IDENTITY_FAILED')
    z.out.parent.mkdir(parents=True,exist_ok=True)
    z.out.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print('F83_REAL_C_TWO_GRID_ACCEPTED_NOT_MICROPHYSICALLY_CERTIFIED',json.dumps(audit['grids'],sort_keys=True),flush=True)

if __name__=='__main__':main()
