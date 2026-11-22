"""F46: direct 346.536369-Hz general relativistic RNS mass-radius curves
for seven F42 explicitly NEW, nonunique first-law candidate EOS.

The 1.95-2.10 M_sun comparison window is PREDECLARED and common across EOS.
Exploration outside it is separate and never silently called a stable branch.
No physical EOS-family certification / X-PSI photon likelihood / Bayes output.
"""
from __future__ import annotations
import argparse, hashlib, io, json, math, sys, zipfile
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'f44'))
import f44_seven_new_candidate_rns as prev

F44_SHA='b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98'
F42_SHA=prev.F42_SHA
COMMON_LO,COMMON_HI=1.95,2.10
OBSERVED_FREQ=346.536369
# Reference exact mass 2.073 is inserted in addition to common curve grid.
MASS_GRID=tuple(sorted(set([round(float(x),8) for x in np.linspace(COMMON_LO,COMMON_HI,21)]+[2.073])))
EXPLORATORY=(1.89,1.92,2.125,2.15,2.175)
MASS_TOL=1.0e-4
HZ_TOL=0.01


def sha(blob):
 if isinstance(blob,Path):blob=blob.read_bytes()
 return hashlib.sha256(blob).hexdigest()


def check_archives(f42, f44):
 if sha(f42)!=F42_SHA or sha(f44)!=F44_SHA:raise ValueError('PINNED_INPUT_ARCHIVE_SHA_MISMATCH')
 with zipfile.ZipFile(f44) as z:
  if z.testzip() is not None:raise ValueError('F44_ARCHIVE_CRC_INVALID')
  data=json.loads(z.read('F44_direct_RNS_seven_candidates.json'))
  if data['direct_fine_fixed_mass_spin_roots']!=7 or set(data['eos'])!=set(prev.EOS):
   raise ValueError('F44_ANCHOR_SET_INCOMPLETE')
  return data


def validate_root(root,mass):
 if not all(math.isfinite(float(root[k])) for k in ('mass_msun','spin_hz','radius_eq_km','central_energy_density_g_cm3','axis_ratio')):
  return False
 return (abs(root['mass_msun']-mass)<=MASS_TOL and abs(root['spin_hz']-OBSERVED_FREQ)<=HZ_TOL
         and .25e15 <= root['central_energy_density_g_cm3'] <= 4.5e15
         and .85 <= root['axis_ratio']<=1. and 6<root['radius_eq_km']<30)


def direct_fixed_mf(binary,table,target,seed, *, eval_model=None):
 """Warm-started direct C/GR 2D root, no interpolation of star outputs.

 Every accepted solution gets an uncached direct C execution at optimizer root.
 The caller can inject an exact deterministic mock for tests only.
 """
 if not(.5<target<3.0):raise ValueError('mass target out of scientific range')
 if eval_model is None:eval_model=prev.eval_rns
 x0=np.array([seed['central_energy_density_g_cm3']/1e15, seed['axis_ratio']],float)
 if not(.25<=x0[0]<=4.5 and .85<=x0[1]<=1.):raise ValueError('seed outside supported RNS root domain')
 cache={};failures=[]
 def residual(x):
  key=(round(float(x[0]),12),round(float(x[1]),12))
  if key not in cache:
   try:cache[key]=eval_model(binary,table,float(x[0])*1e15,float(x[1]))
   except (ValueError,RuntimeError,TimeoutError) as exc:
    failures.append({'x':[float(t) for t in x],'error':type(exc).__name__+':'+str(exc)[:300]})
    return [1e4,1e4]
  s=cache[key]
  return [(s['mass_msun']-target)/.005,(s['spin_hz']-OBSERVED_FREQ)/5.]
 start=np.clip(x0,[.25001,.85001],[4.49999,.99999])
 try:
  fit=least_squares(residual,start,bounds=([.25,.85],[4.5,1.0]),
    diff_step=3e-5,xtol=2e-10,ftol=1e-10,gtol=1e-10,max_nfev=36)
  root=eval_model(binary,table,float(fit.x[0])*1e15,float(fit.x[1]))
  root.update({'target_mass_msun':float(target),'optimizer_status':int(fit.status),
               'optimizer_evals':int(fit.nfev),'direct_solver':True,
               'mass_error_msun':float(root['mass_msun']-target),
               'spin_error_hz':float(root['spin_hz']-OBSERVED_FREQ),
               'seed_center_density_g_cm3':float(seed['central_energy_density_g_cm3']),
               'seed_axis_ratio':float(seed['axis_ratio'])})
  if not validate_root(root,target):
   return {'status':'NO_MATCHED_ROOT','reason':'mass_spin_or_physical_output_gate',
           'root':root,'failures':failures[:15]}
  return {'status':'MATCHED_DIRECT_C_GR_ROOT','root':root,'failures':failures[:15]}
 except (RuntimeError,ValueError,TimeoutError) as exc:
  return {'status':'NUMERICAL_ROOT_FAILED','reason':str(exc)[:500],
          'failures':failures[:15]}


def solve_curve(name,table,anchor,binary, *, solve=direct_fixed_mf, exploratory=True):
 if name not in prev.EOS:raise ValueError('invalid EOS identity')
 if not validate_root(anchor,2.073):raise ValueError('bad physical anchor')
 anchor=dict(anchor,target_mass_msun=2.073)
 found={2.073:anchor};results={};failures={}
 # Prioritize physically closest targets to seed from established F44 star.
 masses=[m for m in MASS_GRID if abs(m-2.073)>1e-8]
 if exploratory:masses+=list(EXPLORATORY)
 for m in sorted(masses,key=lambda v:abs(v-2.073)):
  seed=found[min(found,key=lambda x:abs(x-m))]
  outcome=solve(binary,table,m,seed)
  if outcome['status']=='MATCHED_DIRECT_C_GR_ROOT':
   found[float(m)]=outcome['root'];results[str(m)]=outcome['root']
  else:failures[str(m)]=outcome
  print(name, 'mass',m, 'status',outcome['status'],flush=True)
 common_keys=[m for m in MASS_GRID if m in found]
 measured=[found[m] for m in sorted(found) if m in MASS_GRID]
 # Verify ascending M -> ascending energy density for selected rising branch.
 ordered=sorted(measured,key=lambda x:x['target_mass_msun'] if 'target_mass_msun' in x else 2.073)
 monotone=all(b['central_energy_density_g_cm3']>a['central_energy_density_g_cm3']
              for a,b in zip(ordered,ordered[1:]))
 return {'model':name,'status':'COMMON_WINDOW_GRID_COMPLETE_NOT_GLOBAL_STABILITY_PROOF'
             if len(common_keys)==len(MASS_GRID) and monotone else 'PARTIAL_UNCERTIFIED_MASS_SUPPORT',
         'common_mass_grid':list(MASS_GRID),'successful_common_targets':len(common_keys),
         'common_window_all_roots_present':len(common_keys)==len(MASS_GRID),
         'rising_density_order_pass':monotone,'roots':results,
         'anchor':anchor,'failures':failures,
         'all_succeeded_masses':sorted(found),
         'limitations':'Finite root sequence only; cannot infer global fixed-J secular/dynamical stability or source microphysical validity'}


def run(f42,f44,binary,work,out,name):
 if name not in prev.EOS:raise ValueError('unknown selected EOS')
 meta=check_archives(f42,f44)
 _,files=prev.verify_f42(f42,work)
 if any(sha(files[n])!=meta['eos'][n]['model_table_sha256'] for n in prev.EOS):
  raise ValueError('F44_EOS_TABLE_IDENTITY_MISMATCH')
 anchor=meta['eos'][name]['fine_mesh']['root']
 output={'schema':'J0740_F46_F42_new_candidate_fixed_spin_mass_curve_v1',
         'eos':name,'model_label':meta['eos'][name]['model_label'],
         'source_f42_sha256':sha(f42),'source_f44_sha256':sha(f44),
         'rns_binary_sha256':sha(binary),'rns_table_sha256':sha(files[name]),
         'observed_spin_hz':OBSERVED_FREQ,'common_mass_window_msun':[COMMON_LO,COMMON_HI],
         'physics_model_certified':'NOT_ESTABLISHED',
         'global_rotating_stability_certified':'NOT_ESTABLISHED',
         'seven_model_Bayes':'NOT_RUN','status':'STARTED'}
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
 cur=solve_curve(name,files[name],anchor,binary)
 output.update(cur)
 out.write_text(json.dumps(output,indent=2,sort_keys=True,allow_nan=False)+'\n')
 return output


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for x in ['f42','f44','binary','work','out']:p.add_argument('--'+x,type=Path,required=True)
 p.add_argument('--name',choices=prev.EOS,required=True)
 a=p.parse_args()
 j=run(a.f42,a.f44,a.binary,a.work,a.out,a.name)
 print(json.dumps({'eos':a.name,'status':j['status'],'common_successes':j['successful_common_targets'],
                   'common_required':len(MASS_GRID),'rising':j['rising_density_order_pass']}))
 # Store failed candidates as machine-readable evidence, but only count full curve as CI PASS.
 if j['status']!='COMMON_WINDOW_GRID_COMPLETE_NOT_GLOBAL_STABILITY_PROOF':raise SystemExit(2)
if __name__=='__main__':main()
