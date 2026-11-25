import sys,json,math,hashlib
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
p,out=map(Path,sys.argv[1:]);summary={}
def stats(w):
 a=np.array(w);s=logsumexp(a);assert np.isfinite(s);q=np.exp(a-s)
 return dict(logZ=float(s-np.log(len(a))),ESS=float(1/(q@q)),maxW=float(q.max()))
for label in ('ENG','MPA1','MS1','MS1B','WFF1','WFF2','APR4_CAUSAL'):
 runs=[];allw=[]
 for seed in (352001,352003,352007,352011):
  f=next(p.glob('**/F165-'+label+'-'+str(seed)+'/native.json'));d=json.loads(f.read_text());assert d['model']==label and d['seed']==seed and len(d['rows'])==4096 and d['status']=='COMPLETE'
  assert abs(d['reference_start']-d['reference_end'])<1e-6
  w=[];phase=[]
  for i,r in enumerate(d['rows']):
   assert r['index']==i;phase.append(r['phase_positive'])
   if r['status']=='FINITE':
    v=r['logL']-r['logq_mass']-r['logq_nuisance']-math.log(d['support'])
    assert abs(v-r['logweight'])<1e-8 and abs(math.fsum(r['detectors'])-r['logL'])<1e-5
    w.append(v)
   else:assert r['status'] in ('PRIOR_REJECTED','MR_SUPPORT') and r['logweight'] is None;w.append(-math.inf)
  r=stats(w);r['half_logZ']=stats(w[:2048])['logZ'];r['phase_ESS']=[stats([v for v,b in zip(w,phase) if b==s])['ESS'] for s in (False,True)];r['seed']=seed;r['sha256']=hashlib.sha256(f.read_bytes()).hexdigest();r['finite']=int(np.isfinite(w).sum());runs.append(r);allw.extend(w)
 gates=dict(ESS_each_ge100=all(r['ESS']>=100 for r in runs),maxW_le05=all(r['maxW']<=.05 for r in runs),phase_ESS_ge30=all(min(r['phase_ESS'])>=30 for r in runs),half_drift_le01=all(abs(r['logZ']-r['half_logZ'])<=.1 for r in runs),seed_range_le02=max(r['logZ'] for r in runs)-min(r['logZ'] for r in runs)<=.2)
 summary[label]=dict(pooled=stats(allw),runs=runs,gates=gates,accepted=all(gates.values()),mass_fraction=d['mass_fraction'],curve_zip_sha=d['curve_zip_sha'])
 print('F165_ACCEPTANCE',label,json.dumps(summary[label]),flush=True)
z=summary['MPA1']['pooled']['logZ'];passed=all(q['accepted'] for q in summary.values())
for n,q in summary.items():
 q['relative_evidence_estimate_vs_MPA1']=math.exp(q['pooled']['logZ']-z)
 q['branch_conditional_relative_estimate_vs_MPA1']=q['relative_evidence_estimate_vs_MPA1']*summary['MPA1']['mass_fraction']/q['mass_fraction']
out.write_text(json.dumps(dict(status='SEVEN_DERIVED_NUMERICAL_INTEGRALS_ACCEPTED' if passed else 'UNCONVERGED_ESTIMATES_NOT_ACCEPTED',models=summary,limits='Six F164 derived majorants and separate F39 APR4 causal completion; sampled branches, full radio prior once. Not original nuclear EOS, no rotating dynamical eigenmode proof. Numerical likelihood evidence conditional on these explicit curves and source nuisance prior. No final physically certified seven-EOS claim.'),indent=2))
