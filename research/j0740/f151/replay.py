from __future__ import print_function
import os,sys,json,types
import numpy as np
import xpsi
from conditional import forward,draw
config,partial,out=sys.argv[1:]
old=json.load(open(partial)); rows=old['batches'][0]['rows']; assert len(rows)==80
c=np.array(old['proposal_center_logit']);s=np.array(old['proposal_widths_logit'])
rng=np.random.RandomState(92139)
for r in rows:
    assert np.allclose(draw(rng,c,s),r['u'],rtol=0.,atol=1e-14)
u=draw(rng,c,s)
sys.path.insert(0,os.getcwd())
sys.argv=['main_lp40k_Xse001_Dfix.py','@'+config]
assert not any(flag in open(config).read().splitlines() for flag in ('--multinest','--emcee'))
publisher=types.ModuleType('__main__');publisher.__file__=os.path.abspath(sys.argv[0]);g=publisher.__dict__
execfile(publisher.__file__,g,g)
L=g['likelihood'];L.externally_updated=False
names=[p.name for p in L]; assert names==old['names']
control=np.array(g['p'])
seed=np.array(next(r['p'] for r in rows if r['prior_accepted']))
uc=forward(seed,L,names)
p=np.array(L._prior.inverse_sample(np.r_[uc[:2],u]),dtype=float)
assert np.allclose(p[:2],old['mass_radius'],atol=1e-9,rtol=0.)
def evaluate(q,mode):
    if mode=='bypass':os.environ['F151_BYPASS_CUTOFF']='1'
    else:os.environ.pop('F151_BYPASS_CUTOFF',None)
    xpsi.ParameterSubspace.__call__(L,q)
    lp=float(L._prior(q));assert np.isfinite(lp)
    print('F151_MODE_START',mode,q.tolist());sys.stdout.flush()
    v=float(L(q,force=True))
    valid=np.isfinite(v) and v>-1e50
    ds=[float(s.loglikelihood) for grp in L._signals for s in grp] if valid else None
    if valid:assert len(ds)==4 and np.all(np.isfinite(ds)) and abs(sum(ds)-v)<1e-5
    return {'mode':mode,'raw_logL':v if np.isfinite(v) else None,'valid':bool(valid),'detectors':ds}
a=evaluate(control,'original_control')
assert a['valid'] and abs(a['raw_logL']+21863.3486)<.021864
b=evaluate(p,'original_cutoff')
assert not b['valid'],'Expected sentinel not reproduced at next unsaved draw'
d=evaluate(p,'bypass')
e=evaluate(control,'original_control_end')
assert e['valid'] and abs(e['raw_logL']-a['raw_logL'])<1e-6
receipt={'model':old['model'],'sample_index_zero_based':80,'u':u.tolist(),'p':p.tolist(),'replayed_previous_draws':80,'results':[a,b,d,e],'status':'FINITE_WITHOUT_EARLY_CUTOFF' if d['valid'] else 'UNRESOLVED_AFTER_CUTOFF_BYPASS','limitations':'Diagnostic changes only early-return heuristic, not a converged conditional integral or Bayes evidence.'}
with open(out,'w') as f:json.dump(receipt,f,indent=2,allow_nan=False)
print('F151_REPLAY_COMPLETE',receipt['status'])
