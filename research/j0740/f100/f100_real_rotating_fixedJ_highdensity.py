#!/usr/bin/env python3
"""F100: source-locked REAL Einstein-C fixed angular momentum high-density turning-point survey.

Unlike old F99 low-density scan, extends two genuinely different RNS grids across
first GR static TOV mass maximum (Pc~952 MeV fm^-3, rho_c~2.7367e15 g/cm3)
and into high-density branch of the separately derived 1981-node causal cold EOS.

Physical claim permitted: sampled stationary two-grid fixed-J mass maximum;
NOT full rotating dynamical eigenmodes or original 7-EOS photon Bayes.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

DERIVED_SHA='c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
OLD_F99_SHA='5783d464d6cf9d83bfd51449b6fa2b79f9783b5d79f253f4aff20d0042399b10' # overwritten by exact in workflow
# Densities of F100 fixed AFTER independent static TOV calculation, but not adapted to outcomes from new C stars.
DENSITIES=(2.10e15,2.24e15,2.38e15,2.52e15,2.64e15,2.70e15,
           2.76e15,2.82e15,2.88e15,2.96e15,3.06e15,3.20e15,3.36e15,3.54e15)
GRIDS=('151x301','201x401')
RHO_STATIC_MAX=2.736673904e15

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def analyze_one(stars,reference_rho):
 if len({p['requested_rho_g_cm3'] for p in stars})!=len(stars):raise ValueError('DUPLICATE_REAL_NATIVE_C_STARS')
 pts=sorted(stars,key=lambda q:q['reported_rho_g_cm3'])
 rhos=np.asarray([x['reported_rho_g_cm3'] for x in pts],dtype=float)
 masses=np.asarray([x['M_msun'] for x in pts],dtype=float)
 slopes=np.diff(masses)/(np.diff(rhos)/reference_rho)
 signs=np.sign(slopes)
 signchanges=np.where((signs[:-1]>0)&(signs[1:]<0))[0].tolist()
 out={'n_true_C_stars':len(pts),'central_density':rhos.tolist(),
      'masses_Msun':masses.tolist(),'interval_slopes_Msun_per_rho0':slopes.tolist(),
      'strict_positive_slopes':int(np.sum(slopes>0)),
      'strict_negative_slopes':int(np.sum(slopes<0)),
      'sample_peak_at_original_grid_point':int(np.argmax(masses)),
      'sample_peak_rho_g_cm3':float(rhos[np.argmax(masses)]),
      'sample_peak_mass_Msun':float(np.max(masses)),
      'positive_then_negative_slope_signchange_index':signchanges,
      'continuous_turning_point_math_proven':'NO_DISCRETE_RNS_SAMPLES_ONLY',
      'rotating_axisymmetric_dynamical_eigenmodes':'NOT_RUN'}
 if len(pts)>=8 and signchanges:
  # PCHIP is diagnostic interpolation of measured points, NOT physical GR C solution between points.
  p=PchipInterpolator(rhos/1e15,masses)
  if not (0<np.argmax(masses)<len(pts)-1):raise RuntimeError('PEAK_AT_EDGE_NOT_INTERIOR')
  # Numerical PCHIP derivative has exact zero at a local sampled maximum by construction.
  out['interpolated_diagnostic_peak_not_new_C_star_rho_g_cm3']=float(rhos[np.argmax(masses)])
  out['interpolated_peak_is_RNS_equilibrium_direct_C']='NO_PCHIP_ONLY'
 return out

def main(args):
 sys.path[:0]=[str(Path(__file__).resolve().parents[1]/x) for x in ('f81','f89')]
 import f81_exact_mass_spin as F81
 import f89_fixed_j_real_rns as F89
 old=json.loads(Path(args.old_f99).read_text())
 if old['status']!='18_ACTUAL_REAL_C_MODELS_ON_DISTINCT_DERIVED_1981_MODEL_NOT_ORIGINAL' or old['number_of_real_C_stars']!=18:
  raise ValueError('ORIGINAL_F99_18_GENUINE_C_SOURCE_ACCEPTANCE_MISSING')
 if sha(args.eos)!=DERIVED_SHA:raise ValueError('DISTINCT_COLD_EOS_BYTES_CHANGED')
 raw=np.loadtxt(args.eos,skiprows=1)
 if raw.shape!=(1981,4) or not np.all(np.diff(raw,axis=0)>0):raise ValueError('PHYSICAL_EOS_TABLE_INVALID')
 slope=np.diff(raw[:,1])/((np.diff(raw[:,0]))*F81.C**2 if hasattr(F81,'C') else (np.diff(raw[:,0]))*(2.99792458e10)**2)
 if not np.all((slope>0)&(slope<1)):raise ValueError('F99_DERIVED_AFFINE_EOS_NONCAUSAL')
 upper=float(raw[-1,0]); assert max(DENSITIES)<upper
 bins={'151x301':args.rns151,'201x401':args.rns201}
 if any(not Path(p).is_file() for p in bins.values()):raise ValueError('EINSTEIN_C_BOTH_BINARY_MISSING')
 if set(old['grids'])!=set(GRIDS):raise ValueError('OLD_SOURCE_TWO_GRIDS_MISSING')
 oldj=float(old['same_J_cgs_both_grids']);assert 4e48<oldj<6e48
 report={'schema':'J0740_F100_REAL_NEW_HIGH_DENSITY_EINSTEIN_C_FIXEDJ_2GRID_TURNING_SURVEY',
   'status':'IN_PROGRESS_REQUIRES_REAL_C',
   'derived_F99_eos_sha256':DERIVED_SHA,'full_EOS_source_1981_cold_causal_only':True,
   'source_original_APR_EOS_modified_not_original':'DERIVED_SEPARATE_MATTER_MODEL',
   'target_same_J_cgs':oldj,'predeclared_central_densities_g_cm3':DENSITIES,
   'static_maximum_rho_g_cm3_derived_model':RHO_STATIC_MAX,
   'native_Einstein_C_source_recompiled_2_grids':True,
   'two_grid_results':{},'original_7_EOS_native_MR_photon_evidence':'NOT_RUN',
   'real_rotating_dynamical_mode_eigenfrequencies':'NOT_RUN',
   'secular_rotating_instability_above_turn_sufficient_condition':'REQUIRES_NUMERIC_BOTH_GRIDS_AND_EOS_UNIFORM_ROTATION',
   'sampling_method':'14 predeclared genuinely new same-J same-density stations per native mesh, continuing F99 real C source state'}
 out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
 for grid in GRIDS:
  old_stars=old['grids'][grid]['stars'];last=max(old_stars,key=lambda x:x['reported_rho_g_cm3'])
  cmd=float(last['f_commanded_hz'])
  trace=out.parent/('F100_NEW_REAL_EINSTEIN_C_CALLS_'+grid+'.jsonl')
  if trace.exists():raise FileExistsError('DO_NOT_OVERWRITE_REAL_C_CALL_LOG')
  results=[];errors=[]
  for index,rho in enumerate(DENSITIES):
   calls=[]
   def observed(logrho,commanded_hz):
    try:
     s=F81.evaluate_rns(Path(bins[grid]),Path(args.eos),logrho,commanded_hz)
     record={'source_point_index':index,'rho_target_g_cm3':rho,'logrho':logrho,'requested_f_hz':commanded_hz,
          'M_msun':s['M_msun'],'J_cgs':s['J_cgs'],'f_real_hz':s['spin_hz'],'R_eq_km':s['R_equatorial_km'],'real_C_solver':True}
    except Exception as ex:
     record={'source_point_index':index,'rho_target_g_cm3':rho,'logrho':logrho,'requested_f_hz':commanded_hz,'actual_source_C_error':repr(ex)}
     with trace.open('a') as f:f.write(json.dumps(record,allow_nan=False)+'\n')
     calls.append(record);raise
    with trace.open('a') as f:f.write(json.dumps(record,allow_nan=False)+'\n')
    calls.append(record);return s
   try:
    star=F89.root_at_fixed_j(observed,rho,cmd,oldj,upper,real_required=True)
    star['source_point_index']=index
    star['native_attempts']=len(calls)
    assert len(calls)==star['direct_C_evaluations'] and star['J_relative_error']<=3e-5
    results.append(star)
    cmd=float(star['f_commanded_hz'])
    print('F100_REAL_C',grid,index,format(rho,'.6e'),'M',star['M_msun'],'freq_hz',star['f_measured_hz'],'calls',len(calls),flush=True)
   except Exception as ex:
    errors.append({'source_point_index':index,'rho_g_cm3':rho,'error':repr(ex),'actual_source_C_calls':len(calls)})
    print('F100_C_ROOT_FAIL',grid,index,repr(ex),flush=True)
   report['two_grid_results'][grid]={'actual_C_stars':results,'real_C_errors':errors,
     'actual_native_C_calls_logged':sum(1 for _ in trace.open()) if trace.exists() else 0,
     'native_C_trace_sha256':sha(trace) if trace.exists() else None}
   out.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
  report['two_grid_results'][grid]['sampling_diagnostic']=analyze_one(results,float(old['grids'][grid]['stars'][-1]['reported_rho_g_cm3'])) if len(results)>1 else {'status':'INSUFFICIENT_REAL_C_STARS'}
  out.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
 ok=all(len(report['two_grid_results'][g]['actual_C_stars'])==len(DENSITIES) and not report['two_grid_results'][g]['real_C_errors'] for g in GRIDS)
 report['native_real_C_stars']=sum(len(report['two_grid_results'][g]['actual_C_stars']) for g in GRIDS)
 report['new_native_C_calls']=sum(report['two_grid_results'][g]['actual_native_C_calls_logged'] for g in GRIDS)
 if ok:
  a,b=(report['two_grid_results'][g]['sampling_diagnostic'] for g in GRIDS)
  confirmed=bool(a['positive_then_negative_slope_signchange_index'] and b['positive_then_negative_slope_signchange_index'])
  report['two_mesh_sampled_mass_turning_peak_seen']=confirmed
  report['status']='TWO_GRID_SOURCE_REAL_C_SIGN_CHANGE_FOUND_NOT_FULL_DYNAMICAL_MODE' if confirmed else 'TWO_GRID_REAL_C_COMPLETED_NO_SAMPLED_TURNING_IN_RANGE'
 else:report['status']='REAL_C_PARTIAL_NOT_PHYSICS_ACCEPTED'
 out.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
 print('F100_FINAL_REAL_PHYSICS',report['status'],'stars',report['native_real_C_stars'],'calls',report['new_native_C_calls'],flush=True)
 return report

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 for name in ('old-f99','eos','rns151','rns201','out'):parser.add_argument('--'+name,required=True)
 main(parser.parse_args())
