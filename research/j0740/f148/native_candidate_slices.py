from __future__ import print_function, division
import os,sys,json,math,runpy
import numpy as np
import xpsi
# Source: fine static TOV target roots from A01.01.51/J0740_CAUSAL_CANDIDATE_TOV_20261124.zip,
# each paired with its actual fine-grid gravitational mass. These are derived
# P-E models, NOT the original nuclear EOS or rotating-star radii.
CANDIDATES=[
 ('ENG_derived',2.072999256819864,11.398894145865379),
 ('MPA1_derived',2.072998928394349,12.404375443941959),
 ('MS1_derived',2.0729986158826543,14.78392331297736),
 ('MS1B_derived',2.0729993940822244,14.639922366549861),
 ('WFF1_derived',2.073001443483292,9.899946908196716),
 ('WFF2_derived',2.0729998486596912,10.557621759545201),
]
config,out=sys.argv[1:]
sys.path.insert(0,os.getcwd())
sys.argv=['main_lp40k_Xse001_Dfix.py','@'+config]
assert '--multinest' not in open(config).read().splitlines()
assert '--emcee' not in open(config).read().splitlines()
# Publisher uses actual CLI arguments ONLY when __name__ == '__main__'.
# Both sampler flags are disabled, so running as main builds and checks the model only.
# Python 2 runpy temporarily installs and then clears a module namespace.
# Keep a real module object alive: MOS1/MOS2 derive alpha from global PN.
import types
publisher=types.ModuleType('__main__')
publisher.__file__=os.path.abspath(sys.argv[0])
g=publisher.__dict__
execfile(publisher.__file__,g,g)
assert g['PN'] is not None
assert g['MOS1'].instrument['alpha']==g['PN'].instrument['alpha']
assert g['MOS2'].instrument['alpha']==g['PN'].instrument['alpha']
L=g['likelihood']; ref=np.array(g['p'],dtype=float)
assert len(L)==15 and ref.shape==(15,)
assert L.index('mass')==0 and L.index('radius')==1
assert L.index('p__super_radius')==6 and L.index('s__super_radius')==10
assert L.index('p__super_temperature')==7 and L.index('s__super_temperature')==11
L.externally_updated=False
data={'source_commit':'78880035d0a8aba021761266327dc17e28cd4ed6','f147_artifact_id':14906124279,'status':'RUNNING','parameter_names':[p.name for p in L],'limitations':'Fixed/partially varied nuisance parameters, static-radius points used as coordinate-radius hypotheses, not rotating equilibrium, no APR4 inference, not marginalized likelihood or Bayes factors.','rows':[]}
def save():
    with open(out+'.tmp','w') as f:json.dump(data,f,indent=2,allow_nan=False)
    os.rename(out+'.tmp',out)
def evaluate(label,q,mode):
    row={'model':label,'mode':mode,'p':q.tolist()}
    # Prior.__call__ reads the model state, not its optional vector argument.
    xpsi.ParameterSubspace.__call__(L,q)
    lp=float(L._prior(q))
    if not np.isfinite(lp):
        row.update(status='PRIOR_REJECTED',logL=None)
    else:
        v=float(L(q,force=True))
        if not np.isfinite(v) or v<=L.llzero:
            row.update(status='LIKELIHOOD_INVALID',logL=None)
        else:
            vals=[float(s.loglikelihood) for grp in L._signals for s in grp]
            assert len(vals)==4 and all(np.isfinite(vals))
            assert abs(sum(vals)-v)<1e-5
            row.update(status='NATIVE_EVALUATED',logL=v,detector_logL=vals)
    data['rows'].append(row);save()
    print('F148_POINT',label,mode,row['status'],row['logL'])
    return row
first=evaluate('publisher_control',ref.copy(),'start')
assert first['status']=='NATIVE_EVALUATED' and abs(first['logL']+21863.3486)<0.021864
for name,m,r in CANDIDATES:
    q=ref.copy();q[0]=m;q[1]=r
    # Preserve the reference inclination's standardized offset under the
    # source's correlated mass/inclination prior; no prior density is added.
    q[3]+=0.8*0.00304/0.0703*(m-ref[0])
    evaluate(name,q,'reference_nuisance')
    q[6]*=ref[1]/r;q[10]*=ref[1]/r
    # Local conditional temperature grid at approximately fixed physical spot sizes.
    for dt1 in (-0.05,0.,0.05):
        for dt2 in (-0.05,0.,0.05):
            t=q.copy();t[7]+=dt1;t[11]+=dt2
            evaluate(name,t,'scaled_spots_T%+.2f_%+.2f'%(dt1,dt2))
last=evaluate('publisher_control',ref.copy(),'end')
assert last['status']=='NATIVE_EVALUATED' and abs(last['logL']-first['logL'])<1e-6
for n,m,r in CANDIDATES:
    assert any(x['model']==n and x['status']=='NATIVE_EVALUATED' for x in data['rows']),n
assert len(data['rows'])==62
data['status']='NATIVE_SLICES_COMPLETE_NOT_EOS_BAYES';save()
print('F148_NATIVE_SLICE_COMPLETE',len(data['rows']))
