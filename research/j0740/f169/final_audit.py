import sys,json,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f166'))
from audit import verify,stats
MODELS=('MS1',);SEEDS=(368001,368003,368007,368011);N=32768

def main():
 props,native,out=map(Path,sys.argv[1:]);models={}
 for model in MODELS:
  runs=[];pool=[]
  for seed in SEEDS:
   w=[];phase=[]
   for off in range(0,N,4096):
    name='%s_%d_%d'%(model,seed,off);p=(props/(name+'.json')).read_bytes();raw=(native/(('F168' if off<16384 else 'F169')+'-%s-%d-%d'%(model,seed,off))/'native.json').read_bytes();a,b=verify(p,raw);w.extend(a);phase.extend(b)
   assert len(w)==N
   r=stats(w);r.update(seed=seed,half_logZ=stats(w[:N//2])['logZ'],phase_ESS=[stats([v for v,b in zip(w,phase) if b==s])['ESS'] for s in (False,True)],finite=sum(math.isfinite(v) for v in w));runs.append(r);pool.extend(w)
  gates=dict(ESS_each_ge100=all(r['ESS']>=100 for r in runs),maxW_le05=all(r['maxW']<=.05 for r in runs),phase_ESS_ge30=all(min(r['phase_ESS'])>=30 for r in runs),half_drift_le01=all(abs(r['logZ']-r['half_logZ'])<=.1 for r in runs),seed_range_le02=max(r['logZ'] for r in runs)-min(r['logZ'] for r in runs)<=.2)
  models[model]=dict(pooled=stats(pool),runs=runs,gates=gates,accepted=all(gates.values()),n_per_seed=N);print('F168_ACCEPTANCE',model,json.dumps(models[model]),flush=True)
 out.write_text(json.dumps(dict(status='TWO_DERIVED_NUMERICAL_INTEGRALS_ACCEPTED' if all(v['accepted'] for v in models.values()) else 'UNCONVERGED_ESTIMATES_NOT_ACCEPTED',models=models,retained=['MPA1','ENG','APR4_CAUSAL','WFF1','WFF2','MS1B'],scope='F168 MS1 four prefixes plus equal-length disjoint Sobol suffixes. Adaptive extension conditional numerical diagnostics; not an independent fresh replication. Earlier F165/F166 rows not pooled. No dynamic or microphysical certification.'),indent=2,allow_nan=False))
if __name__=='__main__':main()
