import sys,json,math,hashlib
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
p,out=map(Path,sys.argv[1:]);summary={}
def stats(w):
 a=np.array(w);s=logsumexp(a);assert np.isfinite(s);q=np.exp(a-s)
 return dict(logZ=float(s-np.log(len(a))),ESS=float(1/(q@q)),maxW=float(q.max()))
for label in ('MS1','MS1B'):
 runs=[];allw=[]
 for seed in (342001,342003,342007,342011):
  f=next(p.glob('**/F161-'+label+'-'+str(seed)+'/native.json'));d=json.loads(f.read_text());assert d['model']==label and d['seed']==seed and len(d['rows'])==2048 and d['status']=='COMPLETE'
  assert abs(d['reference_start']-d['reference_end'])<1e-6
  w=[];phase=[]
  for i,r in enumerate(d['rows']):
   assert r['index']==i;phase.append(r['phase_positive'])
   if r['status']=='FINITE':
    v=r['logL']-r['logq_mass']-r['logq_nuisance']-math.log(d['support'])
    assert abs(v-r['logweight'])<1e-8 and abs(math.fsum(r['detectors'])-r['logL'])<1e-5
    w.append(v)
   else:assert r['status'] in ('PRIOR_REJECTED','MR_SUPPORT') and r['logweight'] is None;w.append(-math.inf)
  r=stats(w);r['half_logZ']=stats(w[:1024])['logZ'];r['phase_ESS']=[stats([v for v,b in zip(w,phase) if b==s])['ESS'] for s in (False,True)];r['seed']=seed;r['sha256']=hashlib.sha256(f.read_bytes()).hexdigest();r['finite']=int(np.isfinite(w).sum());runs.append(r);allw.extend(w)
 gates=dict(ESS_each_ge100=all(r['ESS']>=100 for r in runs),maxW_le05=all(r['maxW']<=.05 for r in runs),phase_ESS_ge30=all(min(r['phase_ESS'])>=30 for r in runs),half_drift_le01=all(abs(r['logZ']-r['half_logZ'])<=.1 for r in runs),seed_range_le02=max(r['logZ'] for r in runs)-min(r['logZ'] for r in runs)<=.2)
 summary[label]=dict(pooled=stats(allw),runs=runs,gates=gates,accepted=all(gates.values()))
 print('F161_ACCEPTANCE',label,json.dumps(summary[label]),flush=True)
out.write_text(json.dumps(dict(status='NUMERICAL_WITNESS_ACCEPTANCE_ONLY',models=summary,limits='Independent fresh Linux results. Not Windows prefix extension, not physical certification or final seven-EOS evidence.'),indent=2))
