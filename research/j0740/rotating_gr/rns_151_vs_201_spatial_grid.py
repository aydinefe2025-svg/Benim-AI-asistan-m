"""Compare 151x301 vs 201x401 RNS spacetime grids for all seven EOS.

Both models use exactly the SAME pinned 196-point EOS tables and the SAME
central energy densities. This is a spatial-grid sensitivity test, NOT a
full convergence extrapolation, fixed-M comparison, or NICER posterior.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from jester_to_rns import from_jester_npz,write_rns
from rns_benchmark import RNS_COMMIT,run_rns
from axis_ratio_rns import run_rns_at_spin_with_ratio_fallback

EOS=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
JESTER_COMMIT="e6768650ce992abfd1153a6833857572fe5cd230"
BASE_RNS_SHA256="d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"
REF_GRID="151x301"
NEW_GRID="201x401"
MAX_DM_MSUN=.020
MAX_DR_KM=.15

def compare(previous,refined,stage):
    for m in (previous,refined):
        if any(k not in m for k in ('mass_msun','radius_eq_km','central_energy_density_g_cm3','spin_hz_reported')):
            raise ValueError("RNS model missing required properties")
    a,b=previous,refined
    rho0,rho1=float(a['central_energy_density_g_cm3']),float(b['central_energy_density_g_cm3'])
    m0,m1=float(a['mass_msun']),float(b['mass_msun'])
    r0,r1=float(a['radius_eq_km']),float(b['radius_eq_km'])
    if not all(map(math.isfinite,(rho0,rho1,m0,m1,r0,r1))) or rho0<=0 or rho1<=0:
        raise ValueError('RNS invalid model output')
    if not math.isclose(rho0,rho1,rel_tol=5e-6):
        raise ValueError('RNS central density inconsistent between grid sizes')
    if not (0<m0<4 and 0<m1<4 and 6<r0<30 and 6<r1<30):
        raise ValueError('RNS physical mass radius bounds fail')
    if NEW_GRID not in b.get('raw_stdout_tail',''):
        raise ValueError('RNS claimed high grid not documented in solver stdout')
    dm=m1-m0;dr=r1-r0
    passed=bool(abs(dm)<=MAX_DM_MSUN and abs(dr)<=MAX_DR_KM)
    return {'stage':stage,'original_grid':REF_GRID,'refined_grid':NEW_GRID,
            'same_density_g_cm3':rho0,'M_base_Msun':m0,'M_refined_Msun':m1,'delta_M_Msun':dm,
            'R_base_km':r0,'R_refined_km':r1,'delta_R_km':dr,
            'baseline_spin_hz_reported':float(a['spin_hz_reported']),
            'refined_spin_hz_reported':float(b['spin_hz_reported']),
            'screen_pass':passed,'mass_tol_msun':MAX_DM_MSUN,'radius_tol_km':MAX_DR_KM}

def audit(prior,rns_bin,source_dir,output_dir):
    if (prior.get('status')!='ALL_SEVEN_VALIDATED' or prior.get('validated_eos_count')!=7
            or prior.get('jester_upstream_commit')!=JESTER_COMMIT
            or prior.get('rns_upstream_commit')!=RNS_COMMIT
            or set(prior.get('eos',{}))!=set(EOS)):
        raise ValueError('RNS 7EOS validated input identity mismatch')
    out={}
    for name in EOS:
        row=prior['eos'][name]
        try:
            if row['status']!='MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED':
                raise ValueError('Prior model was not validated')
            source=source_dir/(name+'.npz')
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            if sha!=row['source_npz_sha256']:
                raise ValueError('Pinned source NPZ SHA256 mismatch')
            table,metadata=from_jester_npz(source,points=196)
            outpath=output_dir/('eos'+name+'_196pt')
            write_rns(outpath,table)
            table_sha=hashlib.sha256(outpath.read_bytes()).hexdigest()
            if table_sha!=row['rns_table_sha256']:
                raise ValueError(f'196pt EOS table SHA256 differs from validated model: expected={row["rns_table_sha256"]} actual={table_sha} npz={sha} numpy={np.__version__}')
            base_rot=row['rns_rotating_at_target']
            base_static=row['rns_static_at_same_gravitational_mass']
            rot=run_rns_at_spin_with_ratio_fallback(rns_bin,outpath,central_density=float(base_rot['central_energy_density_g_cm3']),spin_hz=float(prior['spin_hz']))
            static=run_rns(rns_bin,outpath,central_density=float(base_static['central_energy_density_g_cm3']),spin_hz=0)
            rot_diff=compare(base_rot,rot,'rotating_same_center')
            sta_diff=compare(base_static,static,'static_same_center')
            out[name]={
                'status':'HIGHER_GRID_SENSITIVITY_SCREEN_PASS' if rot_diff['screen_pass'] and sta_diff['screen_pass'] else 'MATERIAL_GRID_SENSITIVITY',
                'source_npz_sha256':sha,'identical_196pt_rns_table_sha256':table_sha,
                'rotating':rot_diff,'static':sta_diff,
                'new_rotating_solver_mode':rot.get('solver_mode','RNS_C_SETSPIN')}
        except Exception as exc:
            out[name]={'status':'HIGHER_GRID_MODEL_FAILURE','error_type':type(exc).__name__,'reason':str(exc)[:1000]}
        print(name,out[name]['status'],flush=True)
    passed=sum(1 for x in out.values() if x['status']=='HIGHER_GRID_SENSITIVITY_SCREEN_PASS')
    return {'schema':'j0740-source-matched-151x301-vs-201x401-rns-spatial-grid-v1',
            'status':'ALL_SEVEN_SPATIAL_SENSITIVITY_SCREEN_PASS' if passed==7 else 'PARTIAL_SPATIAL_SENSITIVITY_NOT_FINAL',
            'validated_pairs':passed,'required_pairs':7,
            'jester_commit':JESTER_COMMIT,'rns_commit':RNS_COMMIT,
            'baseline_workflow':42353019033,'baseline_rns_json_sha256':BASE_RNS_SHA256,
            'EOS_thermodynamic_input_points':196,
            'comparison':'7 rotating and 7 static actual RNS C star solutions, same EOS table SHA and same central density, MDIVxSDIV 151x301 versus 201x401',
            'tolerance_mass_Msun':MAX_DM_MSUN,'tolerance_radius_km':MAX_DR_KM,
            'cautions':['One grid refinement does NOT prove asymptotic convergence, nor fixed gravitational mass','RNS output prints to 0.001 Msun and 0.01 km','Not X-PSI photon likelihood, causality proof or EOS posterior'],
            'eos':out}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--rns-json',type=Path,required=True)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--jester-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    data=args.rns_json.read_bytes()
    if hashlib.sha256(data).hexdigest()!=BASE_RNS_SHA256:
        raise ValueError('Baseline JSON SHA256 mismatch')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    res=audit(json.loads(data),args.binary,args.jester_dir,args.out.parent)
    args.out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n')
    print('FINAL',res['status'],'PASS',res['validated_pairs'],'/7',flush=True)
    if res['validated_pairs']!=7:
        raise SystemExit('Numerical spatial mesh sensitivity requires review; saved all evidence')

if __name__=='__main__':main()
