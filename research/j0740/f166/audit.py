"""Independent frozen/native row checks; combine prefixes and suffixes without recalculating photons."""
import sys,json,math,hashlib,zipfile
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from split import MODELS,SEEDS,META
def sha(b):return hashlib.sha256(b).hexdigest()
def stats(w):
 a=np.asarray(w,dtype=float);s=logsumexp(a);assert np.isfinite(s)
 q=np.exp(a-s)
 return dict(logZ=float(s-math.log(len(a))),ESS=float(1/(q@q)),maxW=float(q.max()))
def verify(proposal,native):
 p=json.loads(proposal);d=json.loads(native)
 assert d['status']=='COMPLETE' and d['proposal_sha256']==sha(proposal)
 assert len(p['rows'])==len(d['rows'])==4096
 for k in META:assert d[k]==p[k],k
 assert abs(d['reference_start']+21863.348610369474)<1e-5 and abs(d['reference_end']-d['reference_start'])<1e-6
 w=[];phase=[]
 for i,(a,b) in enumerate(zip(p['rows'],d['rows'])):
  assert a['index']==i
  assert all(b[k]==v for k,v in a.items()),i
  phase.append(a['phase_positive'])
  if b['status']=='FINITE':
   assert len(b['p'])==15 and len(b['detectors'])==4
   assert abs(b['p'][0]-a['mass'])<1e-9 and abs(b['p'][1]-a['radius'])<1e-9
   v=b['logL']-a['logq_mass']-a['logq_nuisance']-math.log(p['support'])
   assert math.isfinite(v) and abs(v-b['logweight'])<1e-8 and abs(math.fsum(b['detectors'])-b['logL'])<1e-5
   w.append(v)
  else:
   assert b['status'] in ('PRIOR_REJECTED','MR_SUPPORT') and b['logweight'] is None and b['logL'] is None
   w.append(-math.inf)
 return w,phase
def main():
 props,old,new,out=map(Path,sys.argv[1:]);summary={}
 for model,n in MODELS.items():
  runs=[];pool=[]
  for seed in SEEDS:
   name='%s_%d'%(model,seed)
   w=[];phase=[];hashes=[]
   for off in range(0,n,4096):
    pn=name+('_%d'%off if off else '')+'.json'
    p=(props/pn).read_bytes()
    if off==0:
     f=old/('F165-%s-%d.zip'%(model,seed))
     with zipfile.ZipFile(f) as z:
      assert z.testzip() is None
      raw=z.read(next(x for x in z.namelist() if x.endswith('native.json')))
    else:
     f=new/('F166-%s-%d-%d'%(model,seed,off))/'native.json'
     raw=f.read_bytes()
    a,b=verify(p,raw);w.extend(a);phase.extend(b);hashes.append(sha(raw))
   assert len(w)==n
   r=stats(w);r['half_logZ']=stats(w[:n//2])['logZ'];r['phase_ESS']=[stats([v for v,b in zip(w,phase) if b==s])['ESS'] for s in (False,True)]
   r.update(seed=seed,finite=sum(math.isfinite(v) for v in w),raw_sha256=hashes);runs.append(r);pool.extend(w)
  gates=dict(ESS_each_ge100=all(r['ESS']>=100 for r in runs),maxW_le05=all(r['maxW']<=.05 for r in runs),phase_ESS_ge30=all(min(r['phase_ESS'])>=30 for r in runs),half_drift_le01=all(abs(r['logZ']-r['half_logZ'])<=.1 for r in runs),seed_range_le02=max(r['logZ'] for r in runs)-min(r['logZ'] for r in runs)<=.2)
  summary[model]=dict(pooled=stats(pool),runs=runs,gates=gates,accepted=all(gates.values()),n_per_seed=n)
  print('F166_ACCEPTANCE',model,json.dumps(summary[model]),flush=True)
 out.write_text(json.dumps(dict(status='FOUR_DERIVED_NUMERICAL_INTEGRALS_ACCEPTED' if all(q['accepted'] for q in summary.values()) else 'UNCONVERGED_ESTIMATES_NOT_ACCEPTED',models=summary,retained_F165=['MPA1','ENG','APR4_CAUSAL'],limits='Conditional derived curves, not rotating dynamical or microscopic certification.'),indent=2,allow_nan=False))
if __name__=='__main__':main()
