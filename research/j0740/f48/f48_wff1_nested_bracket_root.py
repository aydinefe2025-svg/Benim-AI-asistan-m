"""F48 genuine direct pinned C-RNS root for ONE missing F46 WFF1 mass node.

Two nested, physically bracketed scalar Brent solves: axis ratio enforces the
observed spin at fixed central density; then central density brackets mass.
No stellar mass-radius interpolation is used for the final star. Initial seeds
from two direct F46 real C roots only. Retain original failed F46 source.
"""
from __future__ import annotations
import argparse,hashlib,io,json,math,sys,zipfile
from pathlib import Path
from scipy.optimize import brentq

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'f44'))
import f44_seven_new_candidate_rns as rns
F44_SHA='b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98'
F46_WFF1_SHA='bc4795ab244cc169f5ee5011c3ba1ac4646926a14c982b94d07808d647a955f3'
MISSING_M=2.0175
TARGET_FREQ=346.536369
MASS_TOL=1e-4
SPIN_TOL=.01


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def locked_inputs(f44,f46,work):
 if sha(f44)!=F44_SHA or sha(f46)!=F46_WFF1_SHA:raise ValueError('F48_SOURCE_ARTIFACT_SHA_MISMATCH')
 with zipfile.ZipFile(f44) as z:
  if z.testzip() is not None:raise ValueError('F44_SOURCE_ZIP_CRC_FAIL')
  ref=json.loads(z.read('F44_direct_RNS_seven_candidates.json'))
  table_name=ref['eos']['WFF1']['model_label']+'.rns'
  table_bytes=z.read('eos_tables/'+table_name)
  if hashlib.sha256(table_bytes).hexdigest()!=ref['eos']['WFF1']['model_table_sha256']:
   raise ValueError('SOURCE_WFF1_EOS_TABLE_IDENTITY_MISMATCH')
 with zipfile.ZipFile(f46) as z:
  if z.testzip() is not None:raise ValueError('F46_WFF1_CRC_FAIL')
  curve=json.loads(z.read('WFF1_fixed_spin_direct_curve.json'))
  if curve['eos']!='WFF1' or curve['status']!='PARTIAL_UNCERTIFIED_MASS_SUPPORT' or curve['successful_common_targets']!=21:
   raise ValueError('EXPECTED_EXACT_WFF1_21_NODE_SOURCE_FAIL_STATE')
  if set(curve['failures']) != {'2.0175','2.125','2.15','2.175'}:
   raise ValueError('WFF1_ORIGINAL_FAILURE_SET_DRIFT')
 work.mkdir(parents=True,exist_ok=True)
 table=work/table_name;table.write_bytes(table_bytes)
 return table,curve


def nested_direct_root(eval_model, lower, upper, target=MISSING_M, spin=TARGET_FREQ, *, trace=None):
 """Direct numerical star at exactly target M,f via nested bracketing.

 The outer mass bracket comes from two independently *already solved* stars;
 ratio bracketing is re-computed from RNS C for every trial central density.
 """
 if trace is None:trace=[]
 if not(lower['mass_msun']<target<upper['mass_msun'] and
        lower['central_energy_density_g_cm3']<upper['central_energy_density_g_cm3']):
  raise ValueError('VALID_DIRECT_RNS_MASS_DENSITY_BRACKET_REQUIRED')
 e0,e1=(float(x['central_energy_density_g_cm3']) for x in (lower,upper))
 r0,r1=(float(x['axis_ratio']) for x in (lower,upper))
 output_cache={}
 def solve_at_ec(ec):
  # ratio roughly increases with center along the fixed-spin branch, but
  # interpolation of *seed only* is allowed; actual star is a C solve.
  s=(ec-e0)/(e1-e0)
  guess=r0+(r1-r0)*s
  lo=max(.85,guess-.002);hi=min(1.,guess+.002)
  def spin_resid(r):
   model=eval_model(ec,r)
   delta=float(model['spin_hz']-spin)
   trace.append({'ec_g_cm3':float(ec),'ratio':float(r),'spin_residual_hz':delta,
                 'mass_msun':float(model['mass_msun'])})
   output_cache[(float(ec),float(r))]=model
   return delta
  a,b=spin_resid(lo),spin_resid(hi)
  if a*b>0:raise ValueError('NO_REAL_FIXED_FREQUENCY_BRACKET_AT_CENTER')
  ratio=brentq(spin_resid,lo,hi,xtol=2e-10,rtol=2e-10,maxiter=45)
  result=eval_model(ec,float(ratio))
  trace.append({'ec_g_cm3':float(ec),'ratio':float(ratio),'spin_residual_hz':result['spin_hz']-spin,
                 'mass_msun':result['mass_msun'],'accepted_fixed_spin_iteration':True})
  if abs(result['spin_hz']-spin)>.01:raise ValueError('INNER_SPIN_ROOT_NOT_ACCEPTABLE')
  return result

 def mass_resid(e_u):
  star=solve_at_ec(float(e_u)*1e15)
  return float(star['mass_msun']-target)
 a=mass_resid(e0/1e15);b=mass_resid(e1/1e15)
 if not(a<0<b):raise ValueError('INDEPENDENT_RNS_MASS_ENDS_LOST_BRACKET')
 ec=brentq(mass_resid,e0/1e15,e1/1e15,xtol=1.0e-10,rtol=2e-10,maxiter=50)*1e15
 root=solve_at_ec(ec)
 if abs(root['mass_msun']-target)>MASS_TOL or abs(root['spin_hz']-spin)>SPIN_TOL:
  raise ValueError('FINAL_DIRECT_C_GR_MASS_SPIN_ROOT_TOLERANCE_FAIL')
 return dict(root,target_mass_msun=target,source='F48_REAL_DIRECT_C_RNS_NESTED_BRENT_NO_INTERPOLATED_STAR',
             mass_residual_msun=root['mass_msun']-target,spin_residual_hz=root['spin_hz']-spin,
             number_of_actual_direct_solver_models=len(trace))


def run(f44,f46,binary,work,out):
 table,source=locked_inputs(f44,f46,work)
 trace=[]
 report={'schema':'F48_real_WFF1_missing_2p0175_root_source_locked_v1','status':'STARTED',
         'source_F44_sha256':F44_SHA,'source_F46_WFF1_failed_archive_sha256':F46_WFF1_SHA,
         'rns_binary_sha256':sha(binary),'table_sha256':sha(table),
         'target_M_msun':MISSING_M,'target_spin_hz':TARGET_FREQ,
         'new_seven_model_Bayes':'NOT_RUN','EOS_physical_microphysics':'NOT_ESTABLISHED',
         'original_F46_WFF1_failed_node_preserved':True,'solver_trace':trace}
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
 lo=source['roots']['2.01'];hi=source['roots']['2.025']
 try:
  star=nested_direct_root(lambda ec,r:rns.eval_rns(binary,table,ec,r),lo,hi,trace=trace)
  report['root']=star
  report['status']='DIRECT_C_GR_WFF1_MISSING_MASS_ROOT_RECOVERED_NOT_PHYSICAL_STABILITY'
  recovered=dict(source)
  recovered['status']='COMMON_WINDOW_GRID_COMPLETE_NOT_GLOBAL_STABILITY_PROOF'
  recovered['roots']=dict(source['roots'],**{'2.0175':star})
  recovered['successful_common_targets']=22
  recovered['common_window_all_roots_present']=True
  recovered['rising_density_order_pass']=all(
      b['central_energy_density_g_cm3']>a['central_energy_density_g_cm3']
      for a,b in zip([recovered['roots'].get(str(m),recovered['anchor']) for m in recovered['common_mass_grid']],
                     [recovered['roots'].get(str(m),recovered['anchor']) for m in recovered['common_mass_grid']][1:]))
  recovered['failures']=dict(source['failures'])
  recovered['failures']['2.0175']['resolved_in_F48']='REAL_NEW_C_GR_ROOT; F46 original failure preserved'
  recovered['F48_physical_stability']='NOT_ESTABLISHED'
  recovered['F48_source_original_failed_21node_sha256']=F46_WFF1_SHA
  recovered['F48_direct_RNS_Root']=star
  path=out.parent/'WFF1_fixed_spin_direct_curve_F48_recovered.json'
  path.write_text(json.dumps(recovered,sort_keys=True,indent=2)+'\n')
  report['recovered_curve_sha256']=sha(path)
  report['recovered_rising_density_order']=recovered['rising_density_order_pass']
  if not recovered['rising_density_order_pass']:
   raise ValueError('F48_RECOVERED_RISING_ORDER_FAILED')
 except Exception as e:
  report['status']='DIRECT_C_GR_WFF1_RESCUE_FAILED_OPEN'
  report['failure']=type(e).__name__+':'+str(e)
  raise
 finally:
  out.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
 print(json.dumps({'status':report['status'],'root':report.get('root',{}),'rising':report.get('recovered_rising_density_order')}))
 return report


def main():
 p=argparse.ArgumentParser()
 for n in ['f44','f46','binary','work','out']:p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();run(a.f44,a.f46,a.binary,a.work,a.out)
if __name__=='__main__':main()
