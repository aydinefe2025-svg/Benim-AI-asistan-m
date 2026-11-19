"""F68 direct RNS diagnostic for the separately named F67 cold PCHIP EOS.

This is exploratory gravity-only work. The low-pressure table starts above
physical vacuum and n0 is arbitrary, so no baryonic mass, fixed-J stability,
or EOS posterior is inferred. Every reported rotating model is a direct RNS C
evaluation at 346.536369 Hz; no interpolated model is reported as a star.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys, tempfile
from pathlib import Path
import numpy as np
from scipy.optimize import brentq

HERE=Path(__file__).resolve().parent
J0740=HERE.parent
sys.path.insert(0,str(J0740/'f67'))
sys.path.insert(0,str(J0740/'rotating_gr'))
from f67_mpa1_pchip_firstlaw_tov import ColdEOS, load_source, root_at_mass, run as run_f67
from rns_benchmark import run_rns, sha256_file
from axis_ratio_rns import run_rns_at_spin_with_ratio_fallback

SPIN_HZ=346.536369
TARGETS=(2.073,2.175,2.200,2.250)
MESHES=(151,196)
SOURCE_SHA='bd1b0c1a0506f37649275bfe401cf985f78b31e7d5dc3023665c49b9e2d0c3ec'
THERMO_SHA='d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22'
F67_REFERENCE_JSON_SHA='811b6b9e3763e77df0e300f54cae0301cdac1cb1c285b09da8f32e23c0aa0dc8'
RNS_COMMIT='97e85d325a33e37f702306414533f6cd77812477'
G=6.67430e-11; C=299792458.0
C2G=C*C/G*1e-3
P2CG=C**4/G*10.0

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def resample_rns_table(thermo_path,points):
    """Convert F67 [P_geo,E_geo,H,n/n0] to pinned RNS [rho,P,H,n] cgs.

    n is deliberately assigned the arbitrary unit n0=1 cm^-3. RNS gravity
    uses P and epsilon; the resulting M0 must not be interpreted physically.
    """
    if points not in MESHES:raise ValueError('F68_MESH_MUST_BE_151_OR_196')
    a=np.loadtxt(thermo_path,comments='#',dtype=float)
    if a.ndim!=2 or a.shape[1]!=4 or len(a)<100:raise ValueError('F68_BAD_F67_THERMO_SHAPE')
    p,e,h,nratio=a.T
    if not np.isfinite(a).all() or np.any(p<=0) or np.any(e<=0) or np.any(nratio<=0) or h[0]<0 or np.any(np.diff(p)<=0) or np.any(np.diff(e)<=0) or np.any(np.diff(h)<=0) or np.any(np.diff(nratio)<=0):
        raise ValueError('F68_F67_TABLE_NOT_STRICTLY_POSITIVE_MONOTONE')
    lp=np.log(p); lpt=np.linspace(lp[0],lp[-1],points); pt=np.exp(lpt)
    et=np.exp(np.interp(lpt,lp,np.log(e)))
    ht=np.interp(lpt,lp,h)
    nt=np.interp(lpt,lp,nratio)
    rows=np.column_stack([et*C2G,pt*P2CG,ht*(C*100)**2+1.0,nt])
    if not np.isfinite(rows).all() or np.any(rows<=0) or not np.all(np.diff(rows[:,0])>0) or not np.all(np.diff(rows[:,1])>0) or not np.all(np.diff(rows[:,2])>0) or not np.all(np.diff(rows[:,3])>0):
        raise ValueError('F68_RNS_CONVERSION_NONMONOTONE')
    return rows

def write_rns(path,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='ascii',newline='\n') as f:
        f.write(str(len(rows))+'\n');np.savetxt(f,rows,fmt='%.15e')

def gate(model,target,spin):
    m=float(model['mass_msun']);r=float(model['radius_eq_km']);hz=float(model['spin_hz_reported'])
    if not (1<m<3 and 7<r<25 and math.isfinite(m+r+hz)):raise ValueError('F68_RNS_NONPHYSICAL_MODEL')
    if abs(m-target)>.0015:raise ValueError(f'F68_MASS_ROOT_RESIDUAL:{m-target}')
    tol=(.25 if model.get('solver_mode')=='RNS_C_SETSPIN' else .10)
    if abs(hz-spin)>tol:raise ValueError(f'F68_SPIN_ROOT_RESIDUAL:{hz-spin}')

def trial_root(binary,table,target,anchor_rho,spin):
    trace=[];cache={}
    def direct(rho):
        key=round(float(rho),3)
        if key in cache:return cache[key]
        if spin==0:
            s=run_rns(binary,table,central_density=float(rho),spin_hz=0.,spin_tolerance_hz=.10)
            s['solver_mode']='RNS_C_STATIC_DIRECT'
        else:
            s=run_rns_at_spin_with_ratio_fallback(binary,table,central_density=float(rho),spin_hz=spin)
        trace.append({'central_energy_density_g_cm3':float(rho),'mass_msun':float(s['mass_msun']),'radius_eq_km':float(s['radius_eq_km']),'spin_hz_reported':float(s['spin_hz_reported']),'solver_mode':s.get('solver_mode','RNS_C_SETSPIN')})
        cache[key]=s;return s
    samples=[];failures=[]
    for f in (.76,.82,.87,.92,.96,1.,1.04,1.09,1.15):
        rho=anchor_rho*f
        try:samples.append(direct(rho))
        except (ValueError,RuntimeError,TimeoutError,OverflowError) as ex:failures.append({'rho':rho,'reason':str(ex)[:300]})
    ordered=sorted(samples,key=lambda x:x['central_energy_density_g_cm3'])
    bracket=None
    for lo,hi in zip(ordered[:-1],ordered[1:]):
        if lo['mass_msun']<=target<=hi['mass_msun'] and hi['mass_msun']>lo['mass_msun']:
            bracket=(lo,hi);break
    if bracket is None:raise RuntimeError('F68_DIRECT_RNS_MASS_BRACKET_MISSING '+json.dumps({'target':target,'masses':[x['mass_msun'] for x in ordered],'failures':failures[:4]}))
    lo,hi=bracket
    rho=brentq(lambda x:direct(x)['mass_msun']-target,lo['central_energy_density_g_cm3'],hi['central_energy_density_g_cm3'],xtol=1e-6,rtol=1e-9,maxiter=45)
    star=direct(rho);gate(star,target,spin)
    clean={k:v for k,v in star.items() if k not in ('raw_stdout_tail','axis_ratio_bisection_trace')}
    allowed_spin_residual=.25 if star.get('solver_mode')=='RNS_C_SETSPIN' else .10
    return {'status':'PASS_DIRECT_RNS_C_ROOT','star':clean,'trace':trace,'failures':failures,'direct_calls':len(trace),'mass_residual_msun':star['mass_msun']-target,'spin_residual_hz':star['spin_hz_reported']-spin,'allowed_spin_residual_hz':allowed_spin_residual}

def execute(source,rns_binary,out_dir):
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    if sha(source)!=SOURCE_SHA:raise ValueError('F68_RAW_LAL_MPA1_SHA_DRIFT')
    # Preserve the historical F67 relative paths so its signed source receipts
    # reproduce byte-for-byte; those files are inputs to this F68 run.
    f67_dir=Path('results/F67');f67_dir.mkdir(parents=True,exist_ok=True)
    thermo=f67_dir/'F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat'
    f67json=f67_dir/'F67_MPA1_PCHIP_COLD_2p073_static_TOV_20261119.json'
    run_f67(Path(source),out=f67json,eos_out=thermo)
    reference=Path('research/j0740/f67/F67_MPA1_PCHIP_COLD_2p073_static_TOV_20261119.json')
    reference_thermo=Path('research/j0740/f67/F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat')
    if sha(reference_thermo)!=THERMO_SHA:raise ValueError('F68_ARCHIVED_F67_TABLE_SHA_DRIFT')
    generated_table=np.loadtxt(thermo,comments='#',dtype=float)
    archived_table=np.loadtxt(reference_thermo,comments='#',dtype=float)
    if (generated_table.shape!=archived_table.shape or not np.allclose(generated_table,archived_table,rtol=2e-14,atol=0.0)):
        delta=(float(np.max(np.abs(generated_table-archived_table))) if generated_table.shape==archived_table.shape else None)
        raise ValueError(f'F68_REGENERATED_F67_NUMERIC_TABLE_DRIFT:{delta}')
    if sha(reference)!=F67_REFERENCE_JSON_SHA:raise ValueError('F68_ARCHIVED_F67_REFERENCE_SHA_DRIFT')
    generated=json.loads(f67json.read_text());archived=json.loads(reference.read_text())
    gm=generated['new_M2p073_PCHIP_root'];am=archived['new_M2p073_PCHIP_root']
    dM=abs(gm['M_msun']-am['M_msun']);dR=abs(gm['R_km']-am['R_km'])
    dP=abs(gm['central_pressure_geom']-am['central_pressure_geom'])
    if (dM>1e-4 or dR>1e-2 or dP>2e-15 or generated['installed_original_MPA1_raw_source_sha256']!=SOURCE_SHA):
        raise ValueError(f'F68_REGENERATED_F67_STATIC_REFERENCE_VALUE_DRIFT:deltaM={dM},deltaR_km={dR},deltaPc={dP},source_match={generated["installed_original_MPA1_raw_source_sha256"]==SOURCE_SHA}')
    raw=load_source(Path(source));eos=ColdEOS(raw,subdivisions=24,quadrature=48)
    report={'schema':'J0740_F68_F67_PCHIP_COLD_DIRECT_RNS_ROTATING_GR_DIAGNOSTIC_V1','model_label':'MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL','status':'IN_PROGRESS','spin_hz':SPIN_HZ,'target_masses_msun':TARGETS,'mesh_points':MESHES,'input_hashes':{'original_LAL_MPA1_raw_sha256':sha(source),'F67_generated_thermo_sha256':sha(thermo),'F67_archived_thermo_sha256':sha(reference_thermo),'F67_regenerated_static_result_sha256':sha(f67json),'F67_archived_static_reference_sha256':sha(reference),'RNS_binary_sha256':sha(rns_binary),'RNS_commit':RNS_COMMIT},'arbitrary_baryon_normalization':'n0=1 cm^-3 by convention only; M0 and fixed-J stability NOT interpretable','surface_status':'F67 lower-pressure table edge is not physical vacuum; radius remains source-cutoff conditional','posterior':'NOT_RUN','native_XPSI':'NOT_RUN','fixed_J_stability':'NOT_RUN','targets':{}}
    report['F67_static_reproduction_comparison']={'generated_minus_archived_M_msun':gm['M_msun']-am['M_msun'],'generated_minus_archived_R_km':gm['R_km']-am['R_km'],'generated_minus_archived_central_pressure_geom':gm['central_pressure_geom']-am['central_pressure_geom'],'numeric_thermodynamic_table_equal_with_rtol_2e-14':True}
    for n in MESHES:
        tab=out_dir/f'F68_PCHIP_COLD_{n}pt.rns';write_rns(tab,resample_rns_table(thermo,n))
        report['targets'][str(n)]={'rns_table_sha256':sha(tab),'masses':{}}
        for target in TARGETS:
            static_f67=root_at_mass(eos,target,method='rm')
            _,ec=eos.state_h(static_f67['central_enthalpy_from_source_min'])
            anchor_rho=ec*C2G
            row={'F67_static_TOV_M_km':[static_f67['M_msun'],static_f67['R_km']],'F67_static_center_energy_density_g_cm3':anchor_rho}
            row['static_rns']=trial_root(rns_binary,tab,target,anchor_rho,0.)
            row['rotating_rns']=trial_root(rns_binary,tab,target,anchor_rho,SPIN_HZ)
            row['static_radius_delta_vs_f67_km']=row['static_rns']['star']['radius_eq_km']-static_f67['R_km']
            row['rotation_expansion_km']=row['rotating_rns']['star']['radius_eq_km']-row['static_rns']['star']['radius_eq_km']
            if abs(row['static_radius_delta_vs_f67_km'])>.20:raise ValueError(f'F68_RNS_STATIC_TOV_CROSSCHECK_FAIL:{n}:{target}:{row["static_radius_delta_vs_f67_km"]}')
            if row['rotation_expansion_km']<=0:raise ValueError(f'F68_ROTATING_RADIUS_NOT_LARGER:{n}:{target}')
            report['targets'][str(n)]['masses'][f'{target:.3f}']=row
            (out_dir/'F68_direct_RNS_result_20261119.json').write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
            print('F68',n,target,'static',row['static_rns']['star']['radius_eq_km'],'rotating',row['rotating_rns']['star']['radius_eq_km'],flush=True)
    mesh={}
    for target in TARGETS:
        a=report['targets']['151']['masses'][f'{target:.3f}']['rotating_rns']['star']['radius_eq_km']
        b=report['targets']['196']['masses'][f'{target:.3f}']['rotating_rns']['star']['radius_eq_km']
        delta=b-a;mesh[f'{target:.3f}']={'R_eq_151_km':a,'R_eq_196_km':b,'delta_196_minus_151_km':delta,'pass_abs_delta_le_0p060_km':abs(delta)<=.060}
    report['mesh_convergence']=mesh
    report['status']='PASS_DIRECT_RNS_TWO_MESH_EXPLORATORY_ONLY' if all(x['pass_abs_delta_le_0p060_km'] for x in mesh.values()) else 'FAIL_MESH_NOT_CONVERGED'
    report['physical_EOS_acceptance']='NOT_ESTABLISHED: F67 alternate interpolant lacks physical vacuum crust, physical n0/mu0, and validated microscopic interpretation'
    report['limitation']='RNS gives direct gravitational equilibria of the F67 numerical table; no evidence of original MPA1 physics, stable fixed-J branch, X-ray likelihood, or EOS Bayes.'
    (out_dir/'F68_direct_RNS_result_20261119.json').write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    if report['status']!='PASS_DIRECT_RNS_TWO_MESH_EXPLORATORY_ONLY':raise RuntimeError('F68_MESH_CONVERGENCE_FAILURE')
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--rns',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    d=execute(a.source,a.rns,a.out_dir);print(json.dumps({'status':d['status'],'mesh_convergence':d['mesh_convergence']},indent=2))
if __name__=='__main__':main()
