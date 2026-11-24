from __future__ import print_function,division
import os,sys,json,types,hashlib,math
import numpy as np
from scipy.special import logsumexp
import xpsi
from conditional import forward
config,points,out=sys.argv[1:]
d=json.load(open(points));label=d['model'];seed=d['seed'];assert label in ('MS1','MS1B') and len(d['rows'])==2048 and d['support']==.24947354926879406
source='CustomPrior_GLS_compressed_scaling_Dfix.py'
assert hashlib.sha256(open(source,'rb').read()).hexdigest()=='ecabb879c38d4e4e343e5e304e1be39d87a7b0a35d7077454e4677ea1458aa93'
sys.path.insert(0,os.getcwd());sys.argv=['main_lp40k_Xse001_Dfix.py','@'+config]
assert not any(x in open(config).read().splitlines() for x in ('--multinest','--emcee'))
publisher=types.ModuleType('__main__');publisher.__file__=os.path.abspath(sys.argv[0]);g=publisher.__dict__;execfile(publisher.__file__,g,g)
L=g['likelihood'];L.externally_updated=False
names=[p.name for p in L]
assert names==['mass','radius','distance','cos_inclination','p__phase_shift','p__super_colatitude','p__super_radius','p__super_temperature','s__phase_shift','s__super_colatitude','s__super_radius','s__super_temperature','XTI__alpha','column_density','PN__alpha']
ref=np.array(g['p']);assert ref.shape==(15,)
def native(p):
 v=float(L(p,force=True));valid=np.isfinite(v) and v>-1e50
 if not valid:return None,None,v if np.isfinite(v) else None
 ds=[float(s.loglikelihood) for group in L._signals for s in group]
 assert len(ds)==4 and np.all(np.isfinite(ds)) and abs(math.fsum(ds)-v)<1e-5
 return v,ds,v
os.environ['F161_BYPASS_CUTOFF']='1'
start,ds,_=native(ref);assert start is not None and abs(start+21863.348610369474)<1e-5
uc=forward(ref,L,names);assert np.allclose(L._prior.inverse_sample(uc.copy()),ref,rtol=1e-8,atol=1e-8)
result={'status':'RUNNING','model':label,'seed':seed,'curve_sha256':d['curve_sha256'],'proposal_sha256':hashlib.sha256(open(points,'rb').read()).hexdigest(),'reference_start':start,'support':d['support'],'rows':[],'scope':'Independent Linux full-curve integral on original numerical RNS witness only; same radio mass prior once. Not physically certified EOS; do not merge with Windows prefixes.'}
def save():
 with open(out+'.tmp','w') as f:json.dump(result,f,allow_nan=False)
 os.rename(out+'.tmp',out)
for i,r in enumerate(d['rows']):
 assert i==r['index'];u=np.array(r['u']);assert u.shape==(13,) and np.all((u>0)&(u<1))
 m=float(r['mass']);rad=float(r['radius']);rr=ref.copy();rr[:2]=[m,rad];mru=forward(rr,L,names)[:2]
 assert abs(mru[0]-r['mass_u'])<1e-10
 row=dict(r);row.update(logL=None,logweight=None,detectors=None,status='MR_SUPPORT')
 if np.all((mru>0)&(mru<1)):
  pp=np.array(L._prior.inverse_sample(np.r_[mru,u]),dtype=float)
  assert np.allclose(pp[:2],[m,rad],rtol=0,atol=1e-9)
  assert np.max(np.abs(forward(pp,L,names)-np.r_[mru,u]))<1e-7
  xpsi.ParameterSubspace.__call__(L,pp);row['p']=pp.tolist()
  row['status']='PRIOR_REJECTED'
  if np.isfinite(L._prior(pp)):
   v,ds,raw=native(pp)
   if v is None:row.update(status='UNRESOLVED_NATIVE',raw_logL=raw)
   else:row.update(status='FINITE',logL=v,detectors=ds,logweight=v-r['logq_mass']-r['logq_nuisance']-math.log(d['support']))
 result['rows'].append(row)
 if (i+1)%64==0:save();print('F161_PROGRESS',label,seed,i+1);sys.stdout.flush()
end,_,_=native(ref);assert end is not None and abs(end-start)<1e-6
result['reference_end']=end
result['status']='COMPLETE' if all(x['status']!='UNRESOLVED_NATIVE' for x in result['rows']) else 'UNRESOLVED'
save();print('F161_NATIVE_COMPLETE',label,seed,result['status'],sum(x['status']=='FINITE' for x in result['rows']))
