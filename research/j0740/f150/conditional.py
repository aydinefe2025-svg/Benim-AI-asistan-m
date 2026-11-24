from __future__ import print_function, division
import os,sys,json,types
import numpy as np
from scipy.stats import truncnorm,skewnorm
from scipy.special import expit,logit,logsumexp
import xpsi

# Exact source inverse transform is the integration measure. Our forward map
# is used ONLY to centre a proposal, and is round-trip checked against it.
def forward(p,L,names):
    u=np.array([(p[i]-L.get_param(n).bounds[0])/
                (L.get_param(n).bounds[1]-L.get_param(n).bounds[0])
                for i,n in enumerate(names)],dtype=float)
    u[0]=truncnorm.cdf(p[0],-5,5,loc=2.082,scale=.0703)
    u[2]=skewnorm.cdf(p[2],1.7,loc=1.002,scale=.227)
    mu=.0427+.8*.00304/.0703*(p[0]-2.082)
    sd=.00304*np.sqrt(1-.8**2)
    lower=min(-10.,(L.get_param(names[3]).strict_bounds[0]-mu)/sd)
    u[3]=truncnorm.cdf(p[3],lower,10.,loc=mu,scale=sd)
    for i in (5,9):
        a,b=L.get_param(names[i]).bounds
        u[i]=(np.cos(p[i])-np.cos(b))/(np.cos(a)-np.cos(b))
    u[12]=truncnorm.cdf(p[12],-5,5,loc=1.,scale=.104)
    u[14]=truncnorm.cdf(p[14],-5,5,loc=1.+.916*(p[12]-1.),scale=.104*np.sqrt(1-.916**2))
    return u

# Defensive mixture: 10% exact uniform cube, 65% local logistic normal,
# 25% broader logistic normal. Full support and explicit normalized density.
def logq(u,c,s):
    if np.any(u<=0.) or np.any(u>=1.):return -np.inf
    y=logit(u)
    jac=-np.sum(np.log(u)+np.log1p(-u))
    def component(k):
        a=s*k
        return -.5*np.sum(((y-c)/a)**2)-np.sum(np.log(a))-.5*len(u)*np.log(2*np.pi)+jac
    return float(logsumexp([np.log(.1),np.log(.65)+component(1.),np.log(.25)+component(3.)]))
def draw(rng,c,s):
    r=rng.rand()
    if r<.1:return np.clip(rng.rand(len(c)),1e-12,1-1e-12)
    return np.clip(expit(c+rng.randn(len(c))*s*(1. if r<.75 else 3.)),1e-12,1-1e-12)
def stats(rows):
    logs=np.array([r['logL']-r['logq'] if r['logL'] is not None else -np.inf for r in rows])
    if not np.any(np.isfinite(logs)):
        return {'log_integral_cube':None,'ess':0.,'max_weight_fraction':None,'relative_mc_se':None}
    sm=logsumexp(logs); w=np.exp(logs-sm)
    ess=1./np.sum(w*w); n=len(w)
    return {'log_integral_cube':float(sm-np.log(n)),'ess':float(ess),
            'max_weight_fraction':float(np.max(w)),
            'relative_mc_se':float(np.sqrt(max(0.,(n/ess-1.)/(n-1.))))}

def main():
    config,source,out,label=sys.argv[1:]
    old=json.load(open(source))
    assert old['status']=='NATIVE_SLICES_COMPLETE_NOT_EOS_BAYES'
    seed=max((r for r in old['rows'] if r['model']==label and r['status']=='NATIVE_EVALUATED'),key=lambda r:r['logL'])
    ref=np.array(seed['p'],dtype=float)
    sys.path.insert(0,os.getcwd())
    sys.argv=['main_lp40k_Xse001_Dfix.py','@'+config]
    assert '--multinest' not in open(config).read().splitlines()
    assert '--emcee' not in open(config).read().splitlines()
    publisher=types.ModuleType('__main__'); publisher.__file__=os.path.abspath(sys.argv[0])
    g=publisher.__dict__;execfile(publisher.__file__,g,g)
    L=g['likelihood']; L.externally_updated=False
    names=[p.name for p in L]
    assert len(names)==15 and names==old['parameter_names']
    assert g['PN'] is not None and g['MOS1'].instrument['alpha']==g['PN'].instrument['alpha']
    uc=forward(ref,L,names); assert np.all((uc>0.)&(uc<1.)),uc
    p=np.array(L._prior.inverse_sample(uc.copy()),dtype=float)
    assert p.shape==ref.shape and np.allclose(p,ref,atol=1e-8,rtol=1e-8),(p,ref)
    z0=logit(uc[2:])
    # Proposal widths in physical units; only affect efficiency, not target.
    widths=np.array([.075,.001,.006,.20,.025,.025,.006,.20,.025,.025,.05,.06,.035])
    scales=[]
    for j,h in enumerate(widths,2):
        x=ref.copy();x[j]+=h
        y=ref.copy();y[j]-=h
        lo=forward(y,L,names)[j]; hi=forward(x,L,names)[j]
        delta=abs(logit(np.clip(hi,1e-6,1-1e-6))-logit(np.clip(lo,1e-6,1-1e-6)))/2
        scales.append(max(.05,min(3.,delta)))
    s=np.array(scales)
    def mapped(v):
        u=np.r_[uc[:2],v]
        p=np.array(L._prior.inverse_sample(u),dtype=float)
        assert len(p)==15 and np.allclose(p[:2],ref[:2],atol=1e-10,rtol=1e-10)
        xpsi.ParameterSubspace.__call__(L,p)
        return p,bool(np.isfinite(L._prior(p)))
    def native(p):
        v=float(L(p,force=True))
        if not np.isfinite(v) or v< -1e50:return None
        ds=[float(x.loglikelihood) for grp in L._signals for x in grp]
        if len(ds)!=4 or not np.all(np.isfinite(ds)) or abs(sum(ds)-v)>1e-5:
            raise ValueError('Detector sum mismatch')
        return v
    # Reproduce F148 seed with same original evaluator before any integration.
    q,ok=mapped(uc[2:]); assert ok
    start=native(q);assert start is not None and abs(start-seed['logL'])<1e-5,(start,seed)
    # Denominator of the conditional source prior is independently estimated.
    rng=np.random.RandomState(81173)
    nprior=2048; accepted=sum(mapped(rng.rand(13))[1] for _ in range(nprior))
    assert accepted>0
    support=accepted/float(nprior)
    result={'status':'RUNNING','model':label,'mass_radius':ref[:2].tolist(),'names':names,'seed_logL':start,
            'proposal_center_logit':z0.tolist(),'proposal_widths_logit':s.tolist(),
            'support':{'draws':nprior,'accepted':accepted,'fraction':support},'batches':[],
            'scope':'13-dimensional original inverse-prior cube integration at fixed M,R. Static derived candidate, not EOS Bayes. Independent support denominator and defensive proposal; require convergence.'}
    def save():
        with open(out+'.tmp','w') as f:json.dump(result,f,indent=2,allow_nan=False)
        os.rename(out+'.tmp',out)
    for batch in range(2):
        rng=np.random.RandomState(92139+batch); rows=[]
        result['batches'].append({'seed':92139+batch,'rows':rows})
        for i in range(256):
            u=draw(rng,z0,s); lq=logq(u,z0,s); p,ok=mapped(u)
            v=native(p) if ok else None
            if ok and v is None:raise ValueError('Numerical failure at accepted source prior point')
            rows.append({'u':u.tolist(),'p':p.tolist(),'logq':lq,'logL':v,'prior_accepted':ok})
            if i%16==15:save();print('F150_PROGRESS',label,batch,i+1);sys.stdout.flush()
        t=stats(rows)
        t['log_conditional_integral']=None if t['log_integral_cube'] is None else t['log_integral_cube']-np.log(support)
        result['batches'][-1]['stats']=t;save()
    a,b=[x['stats'] for x in result['batches']]
    finite=a['log_integral_cube'] is not None and b['log_integral_cube'] is not None
    stable=finite and min(a['ess'],b['ess'])>=50 and max(a['max_weight_fraction'],b['max_weight_fraction'])<=.1 and abs(a['log_integral_cube']-b['log_integral_cube'])<=.5
    q,ok=mapped(uc[2:]);assert ok and abs(native(q)-start)<1e-6
    result['status']='CONDITIONAL_PILOT_PASS' if stable else 'CONDITIONAL_PILOT_UNCONVERGED'
    save();print('F150_COMPLETE',label,result['status'],a,b)
if __name__=='__main__':main()
