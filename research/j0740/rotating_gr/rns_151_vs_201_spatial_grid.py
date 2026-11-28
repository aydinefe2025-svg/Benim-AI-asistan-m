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

def audit(prior,rns_bin,source_dir,output_dir, *, baseline_binary=None):
    if (prior.get('status')!='ALL_SEVEN_VALIDATED' or prior.get('validated_eos_count')!=7
            or prior.get('jester_upstream_commit')!=JESTER_COMMIT
            or prior.get('rns_upstream_commit')!=RNS_COMMIT
            or set(prior.get('eos',{}))!=set(EOS)):
        raise ValueError('RNS 7EOS validated input identity mismatch')
    if baseline_binary is None or not baseline_binary.is_file() or not rns_bin.is_file():
        raise ValueError('Both compiled RNS 151x301 and 201x401 binaries are required')
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
            # An earlier CI runner can produce different last-decimal text SHA
            # for the same pinned NPZ and numpy resampling. Scientific mesh
            # comparison instead uses ONE actual file for BOTH C binaries.
            byte_match=(table_sha==row['rns_table_sha256'])
            base_rot=row['rns_rotating_at_target']
            base_static=row['rns_static_at_same_gravitational_mass']
            base_rot_fresh=run_rns_at_spin_with_ratio_fallback(
                baseline_binary,outpath,
                central_density=float(base_rot['central_energy_density_g_cm3']),
                spin_hz=float(prior['spin_hz']))
            base_sta_fresh=run_rns(
                baseline_binary,outpath,
                central_density=float(base_static['central_energy_density_g_cm3']),
                spin_hz=0)
            if '151x301' not in base_rot_fresh.get('raw_stdout_tail','') or '151x301' not in base_sta_fresh.get('raw_stdout_tail',''):
                raise ValueError('Baseline 151x301 C solver identity not verified in stdout')
            # Source-run reproducibility bridge: even if byte SHA differs in
            # the last decimals, the fresh baseline must physically reproduce
            # the original published-run model at the same central density.
            orig_rot_dm=float(base_rot_fresh['mass_msun'])-float(base_rot['mass_msun'])
            orig_rot_dr=float(base_rot_fresh['radius_eq_km'])-float(base_rot['radius_eq_km'])
            orig_sta_dm=float(base_sta_fresh['mass_msun'])-float(base_static['mass_msun'])
            orig_sta_dr=float(base_sta_fresh['radius_eq_km'])-float(base_static['radius_eq_km'])
            source_bridge_pass=bool(
                max(abs(orig_rot_dm),abs(orig_sta_dm))<=MAX_DM_MSUN and
                max(abs(orig_rot_dr),abs(orig_sta_dr))<=MAX_DR_KM)
            rot=run_rns_at_spin_with_ratio_fallback(
                rns_bin,outpath,
                central_density=float(base_rot['central_energy_density_g_cm3']),
                spin_hz=float(prior['spin_hz']))
            static=run_rns(rns_bin,outpath,
                central_density=float(base_static['central_energy_density_g_cm3']),
                spin_hz=0)
            rot_diff=compare(base_rot_fresh,rot,'rotating_same_center')
            sta_diff=compare(base_sta_fresh,static,'static_same_center')
            passed=source_bridge_pass and rot_diff['screen_pass'] and sta_diff['screen_pass']
            out[name]={
                'status':'HIGHER_GRID_SENSITIVITY_SCREEN_PASS' if passed else 'MATERIAL_GRID_OR_SOURCE_REPRODUCIBILITY_SENSITIVITY',
                'source_npz_sha256':sha,
                'single_identical_196pt_input_to_both_gr_binaries_sha256':table_sha,
                'archived_prior_196pt_input_sha256':row['rns_table_sha256'],
                'byte_match_with_prior_run':byte_match,
                'original_151_model_numeric_bridge_pass':source_bridge_pass,
                'original_151_model_numeric_bridge_delta_M_Msun_rotating':orig_rot_dm,
                'original_151_model_numeric_bridge_delta_R_km_rotating':orig_rot_dr,
                'original_151_model_numeric_bridge_delta_M_Msun_static':orig_sta_dm,
                'original_151_model_numeric_bridge_delta_R_km_static':orig_sta_dr,
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
            'comparison':'7 rotating and 7 static C/GR stars freshly solved with both 151x301 and 201x401 binaries within ONE CI job, on ONE identical source-MD5-confirmed 196pt EOS file per model and the same central density; original archive baseline compared numerically, original file-byte SHA mismatch explicitly retained',
            'tolerance_mass_Msun':MAX_DM_MSUN,'tolerance_radius_km':MAX_DR_KM,
            'cautions':['Two grids do NOT prove continuum convergence or constant gravitational mass','Input source NPZ digest is pinned; output TEXT files may differ bytewise across runners and are explicitly logged','RNS output prints to 0.001 Msun and 0.01 km','Not X-PSI photon likelihood, causality proof or EOS posterior'],
            'eos':out}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--rns-json',type=Path,required=True)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--baseline-binary',type=Path,required=True)
    p.add_argument('--jester-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    data=args.rns_json.read_bytes()
    if hashlib.sha256(data).hexdigest()!=BASE_RNS_SHA256:
        raise ValueError('Baseline JSON SHA256 mismatch')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    res=audit(json.loads(data),args.binary,args.jester_dir,args.out.parent,
              baseline_binary=args.baseline_binary)
    args.out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n')
    print('FINAL',res['status'],'PASS',res['validated_pairs'],'/7',flush=True)
    if res['validated_pairs']!=7:
        raise SystemExit('Numerical spatial mesh sensitivity requires review; saved all evidence')

if __name__=='__main__':main()
