from __future__ import print_function
import os,sys,json,types,glob
import numpy as np
import xpsi
config,source,out=sys.argv[1:]
old=[json.load(open(p)) for p in sorted(glob.glob(os.path.join(source,'*.json')))]
assert len(old)==6 and all(d['status']=='CONDITIONAL_PILOT_UNCONVERGED' for d in old)
sys.path.insert(0,os.getcwd());sys.argv=['main_lp40k_Xse001_Dfix.py','@'+config]
assert not any(flag in open(config).read().splitlines() for flag in ('--multinest','--emcee'))
publisher=types.ModuleType('__main__');publisher.__file__=os.path.abspath(sys.argv[0]);g=publisher.__dict__;execfile(publisher.__file__,g,g)
L=g['likelihood'];L.externally_updated=False
control=np.array(g['p'])
def evaluate(q,bypass):
    if bypass:os.environ['F154_BYPASS_CUTOFF']='1'
    else:os.environ.pop('F154_BYPASS_CUTOFF',None)
    q=np.array(q);xpsi.ParameterSubspace.__call__(L,q);assert np.isfinite(L._prior(q))
    v=float(L(q,force=True));valid=np.isfinite(v) and v>-1e50
    ds=[float(s.loglikelihood) for grp in L._signals for s in grp] if valid else None
    if valid:assert len(ds)==4 and np.all(np.isfinite(ds)) and abs(sum(ds)-v)<1e-5
    return {'raw_logL':v if np.isfinite(v) else None,'valid':bool(valid),'detectors':ds,'bypass':bool(bypass)}
a=evaluate(control,False);assert a['valid'] and abs(a['raw_logL']+21863.3486)<.021864
receipt={'publisher_start':a,'models':[],'status':'RUNNING','limits':'Diagnostic bypass of publisher early-count cutoff only. No unknown sentinel set to zero. Finite values require detector sum check. Fixed derived static M,R, not EOS Bayes.'}
def save():
    with open(out+'.tmp','w') as f:json.dump(receipt,f,indent=2,allow_nan=False)
    os.rename(out+'.tmp',out)
n=0
for d in old:
    rows=[r for b in d['batches'] for r in b['rows']];assert len(rows)==512
    valid=max((r for r in rows if r['status']=='NATIVE_EVALUATED'),key=lambda r:r['logL']-r['logq'])
    m={'model':d['model'],'replays':[]};receipt['models'].append(m)
    v=evaluate(valid['p'],False);w=evaluate(valid['p'],True)
    assert v['valid'] and w['valid'] and abs(v['raw_logL']-valid['logL'])<1e-5 and abs(v['raw_logL']-w['raw_logL'])<1e-6
    m['finite_control']={'original':v,'bypass':w,'F153_logL':valid['logL']}
    for i,r in enumerate(rows):
        if not r['status'].startswith('UNRESOLVED'):continue
        n+=1;print('F154_POINT',d['model'],i,'ORIGINAL');sys.stdout.flush()
        v=evaluate(r['p'],False)
        print('F154_POINT',d['model'],i,'BYPASS');sys.stdout.flush()
        w=evaluate(r['p'],True)
        m['replays'].append({'index':i,'p':r['p'],'u':r['u'],'F153_raw':r['raw_logL'],'original':v,'bypass':w})
        save()
e=evaluate(control,False);assert e['valid'] and abs(e['raw_logL']-a['raw_logL'])<1e-6
assert n==15
receipt['publisher_end']=e;receipt['replayed']=n
receipt['resolved_finite']=sum(r['bypass']['valid'] for m in receipt['models'] for r in m['replays'])
receipt['status']='DIAGNOSTIC_REPLAY_COMPLETE';save()
print('F154_REPLAY_COMPLETE',n,receipt['resolved_finite'])
