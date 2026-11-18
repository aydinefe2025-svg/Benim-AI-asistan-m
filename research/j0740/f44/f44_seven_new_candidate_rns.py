"""F44: seven distinct F42 new candidate rotating full-GR RNS roots at J0740 M,f.

This is a source-locked numerical pilot, not a physically certified nuclear EOS
family, a global rotating stability proof, or final seven-EOS model Bayes.
"""
from __future__ import annotations
import argparse,hashlib,json,math,io,zipfile,subprocess
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

F42_SHA='c8d8cdc9804a702860ab1af65b60fa25dfac0f74fce9ec6347c4271ea3353115'
TARGET_M=2.073
TARGET_HZ=346.536369
M_TOL=0.0015
HZ_TOL=0.05
EOS=('APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2')


def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return h.hexdigest()


def verify_f42(artifact,work):
 if sha(artifact)!=F42_SHA:raise ValueError('F42_SOURCE_SHA_MISMATCH')
 work.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(artifact) as z:
  if z.testzip() is not None:raise ValueError('F42_ZIP_CRC_FAIL')
  report=json.loads(z.read('F42_candidate_build_report.json'))
  if set(report['results'])!=set(EOS):raise ValueError('Wrong F42 source EOS candidate set')
  files={}
  for name in EOS:
   x=report['results'][name]
   filename=x['new_model_label']+'.rns'
   if name in filename and len(filename.encode('ascii'))>=70:raise ValueError('RNS filename too long')
   blob=z.read(filename)
   if hashlib.sha256(blob).hexdigest()!=x['new_rns_SHA256']:raise ValueError('RNS_EOS_TABLE_SHA_MISMATCH:'+name)
   p=work/filename
   p.write_bytes(blob);files[name]=p
  return report,files


def parse_rns(stdout,ec,ratio):
 candidates=[]
 for line in stdout.splitlines():
  words=line.split()
  if len(words)!=5:continue
  try:values=[float(x) for x in words]
  except ValueError:continue
  if all(math.isfinite(x) for x in values[:4]):candidates.append(values)
 if len(candidates)!=1:raise ValueError('RNS geometric row absent or ambiguous')
 echo,m,r,f,m0=candidates[0]
 if not(.5<m<3.5 and 6<r<30 and 0<=f<2000):raise ValueError('RNS geometric row unphysical')
 if abs(echo-ec/1e15)>1e-7:raise ValueError('RNS wrong center density echo')
 return {'central_energy_density_g_cm3':ec,'axis_ratio':ratio,
         'mass_msun':m,'radius_eq_km':r,'spin_hz':f,
         'baryonic_M0':'NOT_INTERPRETED_SOURCE_CALIBRATION_NOT_CERTIFIED'}


def eval_rns(binary,table,ec,ratio):
 if not (.25e15<=ec<=4.5e15 and .85<=ratio<=1.0):raise ValueError('RNS solver search outside physical domain')
 proc=subprocess.run([str(binary.resolve()),'-f','./'+table.name,
   '-e',f'{ec:.12g}','-r',f'{ratio:.10f}'],cwd=table.parent,
   capture_output=True,text=True,timeout=150)
 if proc.returncode:raise RuntimeError(f'RNS failed exit={proc.returncode}: '+proc.stderr[-300:])
 return parse_rns(proc.stdout,ec,ratio)


def solve_one(binary,table,static_density,*,seed_ratios=(.985,.970,.995)):
 """Two-variable bounded least squares in central energy density and axial ratio.

 Aborted/failed solver calls are captured; nearest valid root must be from a
 direct RNS evaluation, never interpolated mass or radius.
 """
 if not (.30e15<static_density<4.0e15):raise ValueError('invalid locked F43 static-density seed')
 attempts=[];solutions=[]
 for ratio in seed_ratios:
  seed=np.array([static_density/1e15*.97,ratio],dtype=float)
  if not (.26<seed[0]<4.4):continue
  cache={}
  def fun(x):
   k=(round(float(x[0]),11),round(float(x[1]),11))
   if k in cache:v=cache[k]
   else:
    try:v=eval_rns(binary,table,float(x[0])*1e15,float(x[1]))
    except Exception as ex:
     attempts.append({'at':[float(x[0]),float(x[1])],'error':type(ex).__name__+':'+str(ex)[:240]})
     return [1e3,1e3]
    cache[k]=v
   return [(v['mass_msun']-TARGET_M)/.01,(v['spin_hz']-TARGET_HZ)/10]
  try:
   opt=least_squares(fun,seed,bounds=([.25,.85],[4.5,1.]),
                     diff_step=4e-5,xtol=2e-11,ftol=1e-11,gtol=1e-11,
                     max_nfev=45,verbose=0)
   # One more exact direct source C call at returned root (no synthetic surrogate).
   ans=eval_rns(binary,table,float(opt.x[0])*1e15,float(opt.x[1]))
   residual=[ans['mass_msun']-TARGET_M,ans['spin_hz']-TARGET_HZ]
   ans.update({'solver_status':int(opt.status),'function_evals':int(opt.nfev),
      'seed':[float(x) for x in seed],'mass_spin_residual':residual})
   if abs(residual[0])<=M_TOL and abs(residual[1])<=HZ_TOL:
    solutions.append(ans)
    if len(solutions)>=2:break
   else:
    attempts.append({'seed':list(seed),'residual':residual,'reason':'TARGET_RESIDUAL_TOL_FAIL'})
  except Exception as exc:
   attempts.append({'seed':list(seed),'error':type(exc).__name__+':'+str(exc)[:250]})
 if not solutions:return {'status':'NOT_VALIDATED_RNS_ROOT','attempts':attempts}
 out={'status':'DIRECT_RNS_MASS_SPIN_ROOT_PASS','root':solutions[0],
       'other_independent_seed':solutions[1] if len(solutions)>1 else None,
       'attempts':attempts}
 if len(solutions)>1:
  out['seed_spatial_radius_delta_m']=1000*(solutions[1]['radius_eq_km']-solutions[0]['radius_eq_km'])
  out['same_grid_seed_delta_r_gate']=abs(out['seed_spatial_radius_delta_m'])<30
 return out


def run(artifact,tov,binfine,bincoarse,work,out):
 source,tables=verify_f42(artifact,work)
 t=json.loads(Path(tov).read_text())
 if t.get('source_F42_artifact_sha256')!=F42_SHA or set(t['eos'])!=set(EOS):raise ValueError('F43_PRECURSOR_IDENTITY_FAIL')
 output={'schema':'J0740_F44_NEW_7EOS_RNS_FIXED_MASS_AND_SPIN_PILOT_V1',
         'fixed_mass_msun':TARGET_M,'fixed_frequency_hz':TARGET_HZ,
         'f42_sha256':F42_SHA,'f43_sha256':sha(tov),
         'rns_fine_binary_sha256':sha(binfine),
         'rns_coarse_binary_sha256':sha(bincoarse),
         'model_7EOS_Bayes':'NOT_RUN','native_photon_likelihood':'NOT_RUN',
         'global_rotating_stability':'NOT_ESTABLISHED',
         'physical_7candidate_acceptance':'NOT_ESTABLISHED','eos':{},
         'status':'PARTIAL_NOT_FINAL'}
 def save():Path(out).write_text(json.dumps(output,indent=2,sort_keys=True,allow_nan=False)+'\n')
 save()
 for name,table in tables.items():
  static=t['eos'][name]['first_stable_2p073_root']['fine']
  record={'model_label':source['results'][name]['new_model_label'],
    'model_table_sha256':sha(table),
    'source_energy_lift_fraction':source['results'][name]['max_source_energy_fractional_lift'],
    'static_tov_radius_km':static['radius_km']}
  record['fine_mesh']=solve_one(binfine,table,static['center_density_g_cm3'])
  if record['fine_mesh']['status']=='DIRECT_RNS_MASS_SPIN_ROOT_PASS':
   root=record['fine_mesh']['root']
   record['spin_minus_static_radius_km']=root['radius_eq_km']-static['radius_km']
   record['coarse_mesh']=solve_one(bincoarse,table,static['center_density_g_cm3'],seed_ratios=(float(root['axis_ratio']),))
   if record['coarse_mesh']['status']=='DIRECT_RNS_MASS_SPIN_ROOT_PASS':
    record['mesh_radius_delta_m']=1000*(record['coarse_mesh']['root']['radius_eq_km']-root['radius_eq_km'])
    record['mesh_abs_R_gate_30m']=abs(record['mesh_radius_delta_m'])<30
  output['eos'][name]=record;save()
  print(name,record['fine_mesh']['status'],record.get('spin_minus_static_radius_km'),flush=True)
 count=sum(x['fine_mesh']['status']=='DIRECT_RNS_MASS_SPIN_ROOT_PASS' for x in output['eos'].values())
 output['direct_fine_fixed_mass_spin_roots']=count
 output['status']='ALL_SEVEN_DIRECT_ROTATING_RNS_NUMERICAL_ROOTS_PASS_NOT_PHYSICAL_OR_BAYES' if count==7 else 'PARTIAL_NUMERICAL_RNS_ROOTS_NOT_FINAL'
 save()
 return output


def main():
 p=argparse.ArgumentParser();p.add_argument('--f42',type=Path,required=True)
 p.add_argument('--f43',type=Path,required=True);p.add_argument('--fine',type=Path,required=True)
 p.add_argument('--coarse',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();r=run(a.f42,a.f43,a.fine,a.coarse,a.work,a.out)
 print('FINAL_STAGE',r['status'])
 if r['direct_fine_fixed_mass_spin_roots']!=7:raise SystemExit(2)

if __name__=='__main__':main()
