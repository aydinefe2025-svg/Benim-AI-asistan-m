import json,sys,math,subprocess,hashlib
from pathlib import Path
import numpy as np
from scipy.optimize import brentq
binary,out=sys.argv[1:];binary=str(Path(binary).resolve());out=Path(out)
ref=json.loads((out/'inputs.json').read_text());seed=ref['seed_rho'];upper=ref['upper_rho'];grid=ref['grid']
C=2.99792458e10;G=6.673e-8;MSUN=1.989e33
mass_scale=G*MSUN/1.3271244e26;target=2.073/mass_scale;freq=346.536369
journal=out/'native_calls.jsonl';assert not journal.exists()
cache={}
def evaluate(rho,option,value):
 key=(float(rho),option,float(value))
 if key in cache:return cache[key]
 args=[binary,'-f','model.rns','-e','%.17e'%rho,option,'%.17e'%value]
 p=subprocess.run(args,capture_output=True,text=True,timeout=180)
 rec=dict(rho=rho,option=option,value=value,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
 with journal.open('a') as f:f.write(json.dumps(rec,allow_nan=False)+'\n')
 lines=[x for x in p.stdout.splitlines() if x.startswith('F164_NATIVE ')]
 if p.returncode!=0 or len(lines)!=1:raise RuntimeError('C failed '+str(rec)[-600:])
 v=list(map(float,lines[0].split()[1:]));assert len(v)==7 and np.all(np.isfinite(v)),v
 r=dict(rho=v[0]*1e15,M_rns=v[1],M_msun=v[1]*mass_scale,R_km=v[2],f=v[3],J=v[4],Mb_rns=v[5],f_K=v[6],command=option,value=value)
 assert abs(r['rho']/rho-1)<1e-8 and 0<r['M_rns']<4 and 0<r['R_km']<100 and r['Mb_rns']>0
 cache[key]=r;return r
def axis_root(rho,field,target):
 if field=='f':scale=1.
 else:scale=target
 def residual(x):return (evaluate(rho,'-r',x)[field]-target)/scale
 hi=1.;lo=None
 for a in (.995,.99,.98,.96,.94,.90,.85,.80,.75):
  if residual(a)>=0:lo=a;break
 if lo is None:raise RuntimeError('axis bracket unavailable')
 x=brentq(residual,lo,hi,xtol=1e-9,rtol=1e-12,maxiter=30);return evaluate(rho,'-r',x)
def at_spin(rho):
 try:
  r=evaluate(rho,'-s',freq)
  if abs(r['f']-freq)>.05:raise RuntimeError('actual spin mismatch')
 except Exception:r=axis_root(rho,'f',freq)
 assert abs(r['f']-freq)<=.05 and r['J']>0 and r['f_K']>r['f']
 return r
static=evaluate(seed,'-s',0.)
assert abs(static['M_rns']-ref['static'][-1]['M_msun'])<.003 and abs(static['R_km']-ref['static'][-1]['R_km'])<.025,(static,ref['static'])
# Fixed frequency sequence, not fixed-J stability. Retain any failed native calls.
rhos=np.geomspace(.40*seed,min(3.0*seed,.97*upper),29)
assert rhos[0]<seed<rhos[-1];stars=[];errors=[]
for rho in rhos:
 try:
  star=at_spin(float(rho));stars.append(star);print('F164_REAL_SPIN',ref['model'],grid,star,flush=True)
 except Exception as e:errors.append(dict(rho=float(rho),error=repr(e)));print('F164_SCAN_FAIL',rho,repr(e),flush=True)
def save(report):
 (out/'result.json').write_text(json.dumps(report,indent=2,allow_nan=False))
report=dict(status='SCAN_COMPLETE',scope='Exact derived cold barotrope native RNS with modified EOS lookups; original EOS not certified; local fixed-J samples not dynamical eigenmodes',inputs=ref,static_native=static,scan=stars,scan_errors=errors,target_msun=2.073,target_spin=freq)
save(report)
assert len(stars)>=20
pairs=[(a,b) for a,b in zip(stars,stars[1:]) if a['M_rns']<target<=b['M_rns']]
assert pairs,'No sampled increasing mass target bracket'
a,b=pairs[0];r=brentq(lambda x:at_spin(float(np.exp(x)))['M_rns']-target,np.log(a['rho']),np.log(b['rho']),xtol=1e-9,rtol=1e-12,maxiter=30);base=at_spin(float(np.exp(r)));assert abs(base['M_msun']-2.073)<2e-5
report['target']=base;save(report)
j=base['J'];fixed=[];fixed_errors=[]
# Local necessary screen, and broader high-density fixed-J survey.
peak=max(stars,key=lambda x:x['M_rns'])['rho']
dens=np.unique(np.r_[base['rho']*np.array([.975,.9875,1.,1.0125,1.025]),np.linspace(base['rho']*1.05,min(1.25*peak,.95*upper),11)])
for rho in dens:
 try:
  if abs(rho/base['rho']-1)<1e-12:rr=base
  else:rr=axis_root(float(rho),'J',j)
  assert abs(rr['J']/j-1)<3e-5 and rr['f']<rr['f_K']
  fixed.append(rr);print('F164_FIXEDJ',ref['model'],grid,rr,flush=True)
 except Exception as e:fixed_errors.append(dict(rho=float(rho),error=repr(e)));print('F164_FIXEDJ_FAIL',rho,repr(e),flush=True)
 report['fixedJ']=fixed;report['fixedJ_errors']=fixed_errors;save(report)
local=[x for x in fixed if abs(x['rho']/base['rho']-1)<=.025000001]
slopes=np.diff([x['M_msun'] for x in local]);report['local_fixedJ_positive']=bool(len(local)==5 and np.all(slopes>0))
broad=np.diff([x['M_msun'] for x in fixed]);report['sampled_fixedJ_turning']=bool(np.any((broad[:-1]>0)&(broad[1:]<0)))
report['status']='NATIVE_EQUILIBRIA_RECORDED';report['binary_sha']=hashlib.sha256(Path(binary).read_bytes()).hexdigest();report['native_call_count']=len(journal.read_text().splitlines());save(report)
print('F164_COMPLETE',ref['model'],grid,'stars',len(stars),'fixedJ',len(fixed),'local_positive',report['local_fixedJ_positive'],'sampled_turn',report['sampled_fixedJ_turning'],flush=True)
