"""F68: direct full-GR RNS cross-check for the distinct F67 PCHIP MPA1 alternative.

The model is MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL, never original MPA1.
Uses exact pinned LALSuite 7.26.4 raw source only as F67 interpolation input.
Performs source-table 151/196 knot comparison, TOV-vs-static-RNS, and actual
direct C roots at 346.536369 Hz for 2.073, 2.175 and 2.250 Msun.
The absent physical crust and arbitrary baryon normalization stay explicit.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
for p in (ROOT/'f67',ROOT/'f62',ROOT/'rotating_gr'):
    sys.path.insert(0,str(p))
from f67_mpa1_pchip_firstlaw_tov import (
    ColdEOS, load_source, root_at_mass, continuous_piecewise_cubic_sound_speed_extrema,
    EOS_LABEL, SOURCE_SHA,
)
from jester_to_rns import C,G,write_rns
from f62_native_mpa1_rotating import trial_root, M_TOL, HZ_TOL
from rns_benchmark import sha256_file

MODEL='MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL'
TARGETS=(2.073,2.175,2.250)
MESHES=(151,196)
SPIN_HZ=346.536369
MESH_RADIUS_TOL_KM=.060
STATIC_TOV_RNS_TOL_KM=.20


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rns_rows(eos:ColdEOS,points:int):
    if points not in MESHES: raise ValueError('F68_UNPINNED_EOS_MESH')
    p=np.geomspace(eos.p0,eos.pmax,points)
    x=np.log(p)
    e=np.exp(eos.spline(x))
    h=np.asarray(eos.inverse_enthalpy_from_logp(x),float)
    n=np.asarray(eos.n_ratio(x,h),float)
    # RNS units and offset exactly mirror the documented F62 converter.
    rho=e*C*C/G*1e-3
    pressure=p*C**4/G*10.
    enthalpy=h*(C*100.)**2+1.
    baryons=n
    rows=np.column_stack((rho,pressure,enthalpy,baryons))
    if (not np.isfinite(rows).all() or np.any(rows<=0)
            or not np.all(np.diff(rows[:,0])>0) or not np.all(np.diff(rows[:,1])>0)
            or not np.all(np.diff(rows[:,2])>0) or not np.all(np.diff(rows[:,3])>0)):
        raise ValueError('F68_RNS_TABLE_INVALID_OR_NONMONOTONE')
    return rows


def run(source:Path,out:Path,table_dir:Path):
    if sha(source)!=SOURCE_SHA: raise ValueError('F68_RAW_SOURCE_SHA_DRIFT')
    raw=load_source(source)
    eos=ColdEOS(raw,subdivisions=24,quadrature=48)
    report={
      'schema':'J0740_F68_MPA1_PCHIP_COLD_DIRECT_RNS_GR_V1',
      'status':'IN_PROGRESS',
      'model_label':MODEL,'not_original_MPA1':True,'not_F42':True,
      'source_raw_sha256':sha(source),'source_raw_rows':int(len(raw)),
      'source_code_sha256':sha(HERE/'f68_mpa1_pchip_cold_rns.py'),
      'rns_caller':'F62 pinned direct C RNS subprocess helpers',
      'rns_spin_target_hz':SPIN_HZ,'target_masses_msun':list(TARGETS),
      'mesh_points':list(MESHES),
      'predeclared_inherited_gates':{
        'mass_abs_tolerance_msun':M_TOL,'spin_abs_tolerance_hz':HZ_TOL,
        '151_vs_196_eq_radius_abs_tolerance_km':MESH_RADIUS_TOL_KM,
        'static_RNS_vs_independent_TOV_abs_tolerance_km':STATIC_TOV_RNS_TOL_KM,
        'threshold_origin':'existing F62 gates; unchanged'},
      'firstlaw_n0':'ARBITRARY; RNS M0 IS NOT A PHYSICAL BARYONIC MASS',
      'surface_pressure':'positive source minimum; true zero-pressure crust NOT_ESTABLISHED',
      'physical_EOS_admissibility':'NOT_ESTABLISHED',
      'native_XPSI_likelihood':'NOT_RUN','EOS_Bayes':'NOT_RUN',
      'targets':{},'mesh_tables':{}
    }
    table_dir.mkdir(parents=True,exist_ok=True)
    for points in MESHES:
        rows=rns_rows(eos,points)
        path=table_dir/f'MPA1_PCHIP_COLD_V1_{points}pt.rns'
        write_rns(path,rows)
        report['mesh_tables'][str(points)]={
          'rows':len(rows),'sha256':sha(path),'bytes':path.stat().st_size,
          'pmin_geom':float(eos.p0),'pmax_geom':float(eos.pmax),
          'n_is_dimensionless_n_over_n0':True}
    failures=[]
    for target in TARGETS:
        key=f'{target:.3f}'
        try:
            static_ref=root_at_mass(eos,target=target,method='rm')
            uv=tov_uv=__import__('f67_mpa1_pchip_firstlaw_tov').tov(
                eos,static_ref['central_pressure_geom'],method='uv')
            extrema=continuous_piecewise_cubic_sound_speed_extrema(eos,static_ref['central_pressure_geom'])
            # Central energy-density anchor derived from the independent TOV root.
            pc=static_ref['central_pressure_geom']
            ec=float(math.exp(float(eos.spline(math.log(pc)))))
            anchor_rho=ec*C*C/G*1e-3
            target_obj={'independent_static_TOV_rm':static_ref,
              'independent_static_TOV_uv_same_center':uv,
              'TOV_rm_uv_abs_delta_R_km':abs(static_ref['R_km']-uv['R_km']),
              'TOV_rm_uv_abs_delta_M_msun':abs(static_ref['M_msun']-uv['M_msun']),
              'piecewise_sound_speed_extrema':extrema,
              'physical_EOS_certification':'NOT_ESTABLISHED',
              'mesh_results':{}}
            for points in MESHES:
                table=table_dir/f'MPA1_PCHIP_COLD_V1_{points}pt.rns'
                entry={'anchor_central_density_g_cm3':anchor_rho}
                for mode,spin in (('static',0.),('rotating',SPIN_HZ)):
                    try:
                        res=trial_root(str(binary_path()),str(table),target,anchor_rho,spin)
                        entry[mode]=res
                    except Exception as ex:
                        entry[mode]={'status':'FAIL_DIRECT_RNS_ROOT',
                                     'error_type':type(ex).__name__,'error':str(ex)[:2000]}
                        failures.append(f'{key}/{points}/{mode}: {type(ex).__name__}: {ex}')
                # Keep numerical comparison explicit, fail-closed.
                if entry.get('static',{}).get('status','').startswith('PASS'):
                    s=entry['static']['star']
                    entry['static_RNS_minus_independent_TOV_R_km']=s['radius_eq_km']-static_ref['R_km']
                    entry['static_TOV_crosscheck_pass']=abs(entry['static_RNS_minus_independent_TOV_R_km'])<=STATIC_TOV_RNS_TOL_KM
                    if not entry['static_TOV_crosscheck_pass']:
                        failures.append(f'{key}/{points}: static RNS vs independent TOV exceeds inherited .20 km gate')
                target_obj['mesh_results'][str(points)]=entry
            target_obj['rotation_mesh_delta_R_km']=None
            a=target_obj['mesh_results']['151'].get('rotating',{})
            b=target_obj['mesh_results']['196'].get('rotating',{})
            if a.get('status','').startswith('PASS') and b.get('status','').startswith('PASS'):
                delta=float(b['star']['radius_eq_km']-a['star']['radius_eq_km'])
                target_obj['rotation_mesh_delta_R_km']=delta
                target_obj['rotation_mesh_converged']=abs(delta)<=MESH_RADIUS_TOL_KM
                if not target_obj['rotation_mesh_converged']:
                    failures.append(f'{key}: 151/196 R_eq delta {delta} km exceeds inherited .060 km gate')
            else:
                target_obj['rotation_mesh_converged']=False
            report['targets'][key]=target_obj
        except Exception as ex:
            report['targets'][key]={'status':'FAIL_STATIC_TOV_ANCHOR',
                'error_type':type(ex).__name__,'error':str(ex)[:2000]}
            failures.append(f'{key}: static TOV anchor {type(ex).__name__}: {ex}')
    report['failure_count']=len(failures)
    report['failures']=failures
    report['status']='PASS_DIRECT_RNS_NUMERICAL_ONLY_NOT_PHYSICAL_EOS' if not failures else 'FAIL_OR_INCOMPLETE_DIRECT_RNS'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return report


def binary_path():
    p=Path('rns-upstream')/'rns'
    if not p.is_file():raise FileNotFoundError('F68_PINNED_RNS_BINARY_MISSING')
    return p.resolve()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--table-dir',type=Path,required=True)
    a=ap.parse_args()
    r=run(a.source,a.out,a.table_dir)
    print(json.dumps({'status':r['status'],'failure_count':r['failure_count'],
                      'targets':list(r['targets'])},sort_keys=True))
    if r['failure_count']: raise SystemExit(1)

if __name__=='__main__':main()
