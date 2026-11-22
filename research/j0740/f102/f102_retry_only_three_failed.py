#!/usr/bin/env python3
"""Retry only the three still-failing native C fixed-J points; preserve all receipts."""
import argparse,hashlib,json,math,sys
from pathlib import Path
import numpy as np
F100_SHA='2f60a33262319a50af39d03641eb0a52375037450964d0f3206ae8687712506f'
F99_SHA='c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
FAILS={'151x301':(12,), '201x401':(11,12)}
GRID=('151x301','201x401')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(a):
 if sha(a.original)!=F100_SHA or sha(a.eos)!=F99_SHA:raise ValueError('F100_OR_F99_SOURCE_HASH_MISMATCH')
 old=json.loads(Path(a.original).read_text())
 if old['native_real_C_stars']!=24 or old['new_native_C_calls']!=399 or old['status']!='REAL_C_PARTIAL_NOT_PHYSICS_ACCEPTED':raise ValueError('F100_SOURCE_RECEIPT_DRIFT')
 for g,idx in FAILS.items():
  assert tuple(x['source_point_index'] for x in old['two_grid_results'][g]['real_C_errors'] if x['error']=="RuntimeError('MEASURED_C_J_MISMATCH')")==idx
 log201=[json.loads(x) for x in Path(a.f101_201_log).read_text().splitlines()]
 recovered=[x for x in log201 if x['source_point_index']==6 and x.get('actual_native_C') is True]
 target=float(old['target_same_J_cgs']);rho6=float(old['predeclared_central_densities_g_cm3'][6])
 good=[x for x in recovered if abs(float(x['J_cgs'])/target-1)<=3e-5 and abs(float(x['rho_g_cm3'])/rho6-1)<1.5e-4]
 if not good:raise ValueError('F101_SINGLE_RECOVERED_C_RECEIPT_MISSING')
 x=good[-1]
 seed={'source_point_index':6,'requested_rho_g_cm3':rho6,'reported_rho_g_cm3':x['rho_g_cm3'],'M_msun':x['M_msun'],'R_eq_km':x['R_eq_km'],'f_measured_hz':x['f_reported_hz'],'f_commanded_hz':x['requested_spin_hz'],'J_measured_cgs':x['J_cgs'],'J_target_cgs':target,'J_relative_error':abs(x['J_cgs']/target-1),'direct_C_evaluations':9,'real_solver_checked':True,'evidence_source':'F101 exact raw C trace; no recalculation'}
 sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'f81'),str(Path(__file__).resolve().parents[1]/'f89')]
 import f81_exact_mass_spin as F81
 import f89_fixed_j_real_rns as F89
 bins={'151x301':Path(a.rns151),'201x401':Path(a.rns201)}
 if sha(bins['151x301'])==sha(bins['201x401']):raise ValueError('TWO_NATIVE_C_MESHES_REQUIRED')
 result={'schema':'F102_ONLY_THREE_PREVIOUSLY_FAILED_F100_REAL_C_ROOTS_TIGHTER_EQUILIBRIUM_CONVERGENCE','status':'INCOMPLETE_REQUIRE_THREE_ACTUAL_C_ROOTS','original_F100_receipt_sha256':F100_SHA,'F99_EOS_sha256':F99_SHA,'F101_success_index6_reused_from_source_trace':seed,'original_24_stars_untouched':True,'original_399_C_calls_untouched':True,'original_four_F100_error_records_preserved':{g:old['two_grid_results'][g]['real_C_errors'] for g in GRID},'new_C_precision_policy':'SetSpin doubles xacc=1e-9; rns equilibrium accuracy 1e-7','physics_or_acceptance_changed':False,'J_relative_tolerance':3e-5,'new_retry_results':{},'patched_native_C_binaries_sha256':{g:sha(bins[g]) for g in GRID},'dynamic_rotating_modes':'NOT_RUN','seven_original_EOS_XPSI_Bayes':'NOT_RUN'}
 out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
 all_pass=True
 for grid,indices in FAILS.items():
  prev=old['two_grid_results'][grid]['actual_C_stars']
  if grid=='201x401':prev=prev+[seed]
  originals={r['source_point_index']:r for r in prev}
  trace=out.parent/f'F102_ONLY_NEW_C_{grid}.jsonl'
  if trace.exists():raise FileExistsError('REFUSE_TO_OVERWRITE_ANY_NATIVE_C_TRACE')
  new=[];failed=[];count=0
  for i in indices:
   rho=float(old['predeclared_central_densities_g_cm3'][i]);base=originals[max(j for j in originals if j<i)]['f_commanded_hz']
   def ev(lr,cmd):
    nonlocal count
    try:
     s=F81.evaluate_rns(bins[grid],Path(a.eos),lr,cmd)
     row={'source_point_index':i,'rho_g_cm3':rho,'requested_spin_hz':float(cmd),'actual_native_C':True,'M_msun':s['M_msun'],'J_cgs':s['J_cgs'],'f_reported_hz':s['spin_hz'],'R_eq_km':s['R_equatorial_km']}
    except Exception as e:
     row={'source_point_index':i,'rho_g_cm3':rho,'requested_spin_hz':float(cmd),'actual_native_C_error':repr(e)}
     with trace.open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
     count+=1;raise
    with trace.open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
    count+=1;return s
   try:
    rec=F89.root_at_fixed_j(ev,rho,base,target,3.60e15,real_required=True);rec['source_point_index']=i
    if rec['direct_C_evaluations']>count:raise ValueError('C_CALL_COUNT_MISMATCH')
    new.append(rec);print('F102_REAL_C_RECOVERED',grid,i,rec['J_relative_error'],flush=True)
   except Exception as e:
    failed.append({'source_point_index':i,'error':repr(e),'new_C_calls':count});print('F102_REAL_C_FAILURE_PRESERVED',grid,i,repr(e),flush=True)
  allstars=sorted(list(originals.values())+new,key=lambda r:r['source_point_index'])
  complete=len(allstars)==14 and [r['source_point_index'] for r in allstars]==list(range(14))
  result['new_retry_results'][grid]={'new_stars':new,'failures':failed,'new_C_calls':count,'stars_14_complete':complete}
  if not complete or failed or any(not r.get('real_solver_checked',False) or r['J_relative_error']>3e-5 for r in allstars):
   all_pass=False
  else:
   rhoarr=np.array([r['reported_rho_g_cm3'] for r in allstars]);mass=np.array([r['M_msun'] for r in allstars]);slopes=np.diff(mass)/np.diff(rhoarr/1e15)
   result['new_retry_results'][grid]['sampled_positive_then_negative_slope']=bool(np.any(slopes>0) and np.any(slopes<0) and np.any((slopes[:-1]>0)&(slopes[1:]<0)))
   result['new_retry_results'][grid]['sample_peak_mass_msun']=float(mass.max())
 if all_pass and all(result['new_retry_results'][g]['sampled_positive_then_negative_slope'] for g in GRID):
  result['status']='28_TWO_GRID_REAL_C_SAME_J_DISCRETE_TURN_NUMERIC_PASS_NOT_DYNAMIC_MODES'
  result['total_C_stars']=28;result['old_C_stars']=24;result['recovered_original_missing_C_stars']=4
  out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print('F102_COMPLETE_28_REAL_C_NUMERIC_ONLY',flush=True)
 else:
  result['status']='THREE_C_ROOTS_NOT_ALL_PASS';result['scientific_claim']='NOT_ACCEPTED'
  out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');raise SystemExit(2)
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for k in ['original','eos','rns151','rns201','out']:p.add_argument('--'+k,required=True)
 p.add_argument('--f101-201-log',dest='f101_201_log',required=True)
 main(p.parse_args())
