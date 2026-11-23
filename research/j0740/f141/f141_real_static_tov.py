#!/usr/bin/env python3
"""F141: true source-native LAL C static TOV on F140 derived six EOS.

Uses the byte-verified F140 GitHub Actions artifact; NEVER reruns F140 or
the 323 original rotating C/RNS stars. This is static GR equilibrium only.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
NAMES=('ENG','MPA1','MS1','MS1B','WFF1','WFF2')
C=299792458.;G=6.67430e-11
P_GEOM_TO_PA=C**4/G
M_SOLAR=1.988409870698051e30
F140_SOURCE_RUN_ID=45259419081
F140_SOURCE_COMMIT='137ede2012b85b66f630f0865b51e2d1a836accd'
F140_SOURCE_ARTIFACT_ID=14859941911
F140_ARTIFACT_ZIP_SHA256='c73eada7da05c015fae75a27f29782aaafc62038a49bc760830f3de4cee6c435'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def verify_f140(root):
    root=Path(root)
    reportpath=root/'F140_NATIVE_COLD_SEAM_RESULT.json'
    ledgerpath=root/'F140_SHA256.json'
    if not reportpath.is_file() or not ledgerpath.is_file():raise ValueError('F140_REAL_ARTIFACT_MISSING')
    report=json.loads(reportpath.read_text());ledger=json.loads(ledgerpath.read_text())
    if report.get('status')!='SIX_DERIVED_LOCAL_NATIVE_LAL_PASS_NOT_GLOBAL' or set(report['models'])!=set(NAMES):
        raise ValueError('F140_REAL_SIX_CANDIDATES_NOT_VERIFIED')
    if len(ledger)!=7:raise ValueError('F140_LEDGER_INCOMPLETE')
    for filename, digest in ledger.items():
        path=root/filename
        if not path.is_file() or sha(path)!=digest:raise ValueError('F140_ARTIFACT_SHA_MISMATCH:'+filename)
    for n in NAMES:
        d=report['models'][n]
        if d['status']!='LOCAL_DERIVED_COLD_NATIVE_LAL_PASS':
            raise ValueError('F140_MODEL_NOT_PASSED:'+n)
        filename=n+'_F140_DERIVED_NOT_ORIGINAL_EOS_SI.txt'
        if ledger.get(filename)!=d.get('derived_eos_sha256'):
            raise ValueError('F140_CANDIDATE_SHA_NOT_MATCHING_SOURCE:'+n)
    return report,ledger

def read_candidate(root,name):
    p=Path(root)/(name+'_F140_DERIVED_NOT_ORIGINAL_EOS_SI.txt')
    a=np.loadtxt(p)
    if a.ndim!=2 or a.shape[1]!=2 or len(a)<300:
        raise ValueError('INVALID_TRUE_F140_CANDIDATE')
    if np.any(~np.isfinite(a)) or np.any(a<=0) or np.any(np.diff(a,axis=0)<=0):
        raise ValueError('INVALID_F140_MONOTONICITY')
    return a

def choose_central_pressure(a,rho_c_g_cm3):
    target=float(rho_c_g_cm3)*1000*G/C**2
    if not (a[5,1]<target<a[-5,1]):raise ValueError('REAL_STAR_CENTRE_OUTSIDE_SOURCE_E_RANGE')
    return float(np.interp(target,a[:,1],a[:,0])),target

def actual_tov(ls,eos,p_center_geom,epsrel):
    if not hasattr(ls,'SimNeutronStarTOVODEIntegrateWithTolerance'):
        raise RuntimeError('LAL_NATIVE_STATIC_GR_TOV_WITH_TOLERANCE_UNAVAILABLE')
    raw=ls.SimNeutronStarTOVODEIntegrateWithTolerance(float(p_center_geom*P_GEOM_TO_PA),eos,float(epsrel))
    if len(raw)!=3:raise RuntimeError('UNEXPECTED_LAL_C_TOV_RETURN_SIGNATURE')
    radius,mass,k2=[float(x) for x in raw]
    if not (all(math.isfinite(x) for x in (radius,mass,k2)) and 4000<radius<40000 and
            0.5<mass/M_SOLAR<4.0 and 0<k2<1):
        raise ValueError(f'UNPHYSICAL_NUMERICAL_LAL_TOV_OUTPUT:{radius}:{mass}:{k2}')
    return {'radius_km':radius/1000,'mass_msun':mass/M_SOLAR,'k2':k2,'epsrel':float(epsrel)}

def compare_convergence(coarse,fine,r_tol=0.005,m_tol=0.005):
    dr=abs(coarse['radius_km']/fine['radius_km']-1.)
    dm=abs(coarse['mass_msun']/fine['mass_msun']-1.)
    if max(dr,dm)>max(r_tol,m_tol):
        raise ValueError(f'LAL_REAL_TOV_TWO_TOLERANCE_NONCONVERGENCE:{dr}:{dm}')
    return {'radius_relative_difference':dr,'mass_relative_difference':dm,
       'pass_two_tolerances':True}

def audit_star_eos_pressure_path(ls,eos,p_c,p_min,points=2001):
    f=getattr(ls,'SimNeutronStarEOSEnergyDensityDerivOfPressureGeometerized',
              None) or getattr(ls,'SimNeutronStarEOSEnergyDensityDerivOfPressureGeometrized')
    grid=np.geomspace(float(p_min)*1.000000001,float(p_c),points)
    d=np.array([float(f(float(x),eos)) for x in grid])
    cs2=np.divide(1.,d,out=np.full_like(d,np.nan),where=d!=0)
    return {'points':int(len(grid)),
            'native_nonpositive_or_nonfinite':int(np.sum(~np.isfinite(cs2)|(cs2<=0))),
            'native_superluminal':int(np.sum(np.isfinite(cs2)&(cs2>1))),
            'min_cs2':float(np.nanmin(cs2)) if np.any(np.isfinite(cs2)) else None,
            'max_cs2':float(np.nanmax(cs2)) if np.any(np.isfinite(cs2)) else None,
            'fully_positive_and_causal_on_scanned_static_path':bool(np.all(np.isfinite(cs2)&(cs2>0)&(cs2<=1)))}

def run(root,star_ref,out):
    import lalsimulation as ls
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    source,ledger=verify_f140(root)
    refs=json.loads(Path(star_ref).read_text())
    if refs.get('schema')!='F139_NEAREST_ORIGINAL_C_STAR_CENTRAL_DENSITIES_FROM_F79_V1' or set(refs.get('models',{})) != set(NAMES)|{'APR4_EPP'}:
        raise ValueError('REAL_F79_STAR_REFERENCE_NOT_FOUND')
    report={'schema':'J0740_F141_REAL_C_SIX_DERIVED_STATIC_TOV_TWO_TOLERANCE_V1',
        'F140_original_native_run_id':F140_SOURCE_RUN_ID,
        'F140_original_commit':F140_SOURCE_COMMIT,
        'F140_artifact_id':F140_SOURCE_ARTIFACT_ID,
        'F140_expected_ZIP_sha256':F140_ARTIFACT_ZIP_SHA256,
        'F140_model_artifact_sha256':ledger,
        'physical_model_status':'SIX_DISTINCT_DERIVED_TABULAR_COLD_EOS_NOT_ORIGINAL_NUCLEAR_EOS',
        'static_GR_C_stars':{},'status':'IN_PROGRESS',
        'global_thermodynamic_gibbs_certification':'NOT_ESTABLISHED',
        'real_rotating_C_stability':'NOT_TESTED',
        'native_photon_bayes_seven_EOS':'NOT_COMPUTED'}
    outpath=out/'F141_REAL_SIX_STATIC_TOV.json'
    for name in NAMES:
        info={'status':'IN_PROGRESS'}
        try:
            a=read_candidate(root,name)
            rho=refs['models'][name]['central_density_g_cm3']
            pc,ec=choose_central_pressure(a,rho)
            fixed=ls.SimNeutronStarEOSFromFile(str((Path(root)/(name+'_F140_DERIVED_NOT_ORIGINAL_EOS_SI.txt')).resolve()))
            # Two actual GR C runs at same pressure, independently varied tolerance.
            coarse=actual_tov(ls,fixed,pc,1e-5)
            fine=actual_tov(ls,fixed,pc,1e-7)
            convergence=compare_convergence(coarse,fine)
            path_gate=audit_star_eos_pressure_path(ls,fixed,pc,float(a[0,0]))
            info={'status':'REAL_STATIC_LAL_C_TOV_TWO_TOLERANCE_COMPLETED',
                  'source_original_rotating_star_centre_density_g_cm3':rho,
                  'centre_selection':'DERIVED_EPSILON_EQ_REFERENCE_RNS_REST_MASS_DENSITY_SCALE_ONLY_NOT_SAME_RNS_STAR',
                  'central_pressure_geom_m_minus2':pc,'target_e_geom_m_minus2':ec,
                  'coarse':coarse,'fine':fine,'convergence':convergence,
                  'full_occupied_pressure_path_native_causality':path_gate,
                  'same_mass_or_same_J_rotating_result':'NO'}
        except Exception as exc: info={'status':'FAIL_CLOSED','error':repr(exc)}
        report['static_GR_C_stars'][name]=info
        outpath.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
        print('F141_REAL_STATIC_TOV',name,info['status'],flush=True)
    report['native_real_two_tolerance_models_passed']=sum(d['status']=='REAL_STATIC_LAL_C_TOV_TWO_TOLERANCE_COMPLETED' for d in report['static_GR_C_stars'].values())
    report['status']='SIX_NATIVE_C_STATIC_TOV_CONVERGED_PHYSICAL_CERTIFICATION_SEPARATE' if report['native_real_two_tolerance_models_passed']==6 else 'PARTIAL_NATIVE_C_STATIC_TOV_FAIL_CLOSED'
    outpath.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    (out/'F141_SHA256.json').write_text(json.dumps({outpath.name:sha(outpath)},sort_keys=True,indent=2)+'\n')
    print('F141_FINAL',report['status'],flush=True)
    return 0 if report['native_real_two_tolerance_models_passed']==6 else 2
if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--F140-root',required=True)
    ap.add_argument('--star-ref',required=True)
    ap.add_argument('--out',required=True)
    a=ap.parse_args()
    raise SystemExit(run(a.F140_root,a.star_ref,a.out))
