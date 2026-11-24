from __future__ import print_function,division
import os,sys,json,types
import numpy as np
from scipy.special import expit,logit,logsumexp
from scipy.stats import multivariate_normal
import xpsi
from conditional import forward
def main():
    config,slices,proposal,out,label,pilot_path,replay_path=sys.argv[1:]
    old=json.load(open(slices)); fit=json.load(open(proposal))
    assert old['status']=='NATIVE_SLICES_COMPLETE_NOT_EOS_BAYES'
    assert fit['source_rows']==379669 and fit['group_disjoint'] and fit['selected_components']==8
    candidate=fit['candidates'][label]
    mr=np.array(candidate['mr']); w=np.array(candidate['weights']); m=np.array(candidate['means']); C=np.array(candidate['covariances'])
    assert np.all(w>0) and abs(w.sum()-1)<1e-10
    chol=np.linalg.cholesky(C); inv=np.linalg.inv(C); norm=-.5*(13*np.log(2*np.pi)+np.linalg.slogdet(C)[1])
    seed=max((r for r in old['rows'] if r['model']==label and r['status']=='NATIVE_EVALUATED'),key=lambda r:r['logL'])
    ref=np.array(seed['p']); assert np.allclose(ref[:2],mr,rtol=0,atol=1e-10)
    sys.path.insert(0,os.getcwd());sys.argv=['main_lp40k_Xse001_Dfix.py','@'+config]
    assert not any(s in open(config).read().splitlines() for s in ('--multinest','--emcee'))
    publisher=types.ModuleType('__main__');publisher.__file__=os.path.abspath(sys.argv[0]);g=publisher.__dict__;execfile(publisher.__file__,g,g)
    L=g['likelihood']; L.externally_updated=False; names=[p.name for p in L]
    assert names==fit['names']==old['parameter_names']
    uc=forward(ref,L,names); p=np.array(L._prior.inverse_sample(uc.copy()))
    assert np.allclose(p,ref,atol=1e-8,rtol=1e-8)
    def mapped(u):
        p=np.array(L._prior.inverse_sample(np.r_[uc[:2],u]),dtype=float)
        assert np.allclose(p[:2],mr,atol=1e-10,rtol=1e-10)
        xpsi.ParameterSubspace.__call__(L,p)
        return p,bool(np.isfinite(L._prior(p)))
    def native(p):
        os.environ['F155_BYPASS_CUTOFF']='1'
        v=float(L(p,force=True))
        if not np.isfinite(v) or v< -1e50:return None,v,'UNRESOLVED_NATIVE_SENTINEL'
        ds=[float(x.loglikelihood) for grp in L._signals for x in grp]
        if len(ds)!=4 or not np.all(np.isfinite(ds)) or abs(sum(ds)-v)>1e-5:
            return None,v,'UNRESOLVED_DETECTOR_SUM'
        return v,v,'NATIVE_EVALUATED'
    # Only past F153/F154 draws train the new proposal. Fresh batches never adapt.
    past=json.load(open(pilot_path))
    replay=json.load(open(replay_path))
    assert past['model']==label and replay['resolved_finite']==15
    fixes={r['index']:r for d in replay['models'] if d['model']==label for r in d['replays']}
    rows=[r for batch in past['batches'] for r in batch['rows']]
    assert len(rows)==512
    for i,r in fixes.items():
        assert rows[i]['p']==r['p'] and rows[i]['u']==r['u'] and r['bypass']['valid']
        rows[i]['logL']=r['bypass']['raw_logL']
    finite=[r for r in rows if r['logL'] is not None]
    y=np.array([logit(r['u']) for r in finite])
    lw=np.array([r['logL']-r['logq'] for r in finite])
    # Select dispersed high-weight anchors, then locally optimise the posterior
    # density in logit coordinates. Old mixture and uniform keep full support.
    from scipy.optimize import minimize
    order=np.argsort(lw)[::-1]; anchors=[]
    for i in order:
        z=y[i]; j=int(np.argmax(np.log(w)+norm-.5*np.einsum('ki,kij,kj->k',z-m,inv,z-m)))
        if all(np.linalg.norm(np.linalg.solve(chol[j],z-t[0]))>1.5 for t in anchors):
            anchors.append((z,j,float(lw[i])))
        if len(anchors)>=8:break
    assert len(anchors)>0
    opt_records=[]
    centres=[]; covs=[]; weights=[]
    for k,(z,j,l) in enumerate(anchors):
        if k<2:
            def objective(t):
                u=expit(z+np.dot(chol[j],t))
                if np.any(u<=0.) or np.any(u>=1.):return 1e50
                pp,ok=mapped(u)
                if not ok:return 1e50
                v,raw,status=native(pp)
                if v is None:return 1e50
                return -v-np.sum(np.log(u)+np.log1p(-u))
            base=objective(np.zeros(13))
            opt=minimize(objective,np.zeros(13),method='Powell',options={'maxfev':240,'xtol':.05,'ftol':1e-7})
            if np.isfinite(opt.fun) and opt.fun<base:
                zz=z+np.dot(chol[j],opt.x)
            else:zz=z.copy()
            opt_records.append({'anchor':k,'objective_before':float(base),'objective_after':float(min(base,opt.fun)),'evaluations':int(opt.nfev)})
            centres.append(zz);covs.append(.4*C[j]);weights.append(2.)
        centres.append(z);covs.append(.6*C[j]);weights.append(1.)
    am=np.array(centres);ac=np.array(covs);aw=np.array(weights);aw/=aw.sum()
    ach=np.linalg.cholesky(ac);ai=np.linalg.inv(ac);an=-.5*(13*np.log(2*np.pi)+np.linalg.slogdet(ac)[1])
    def logq(u):
        yy=logit(u);d=yy-m;v=np.einsum('ki,kij,kj->k',d,inv,d);jac=-np.sum(np.log(u)+np.log1p(-u))
        d=yy-am;av=np.einsum('ki,kij,kj->k',d,ai,d)
        return float(logsumexp([np.log(.02),np.log(.33)+logsumexp(np.log(w)+norm-.5*v)+jac,np.log(.15)+logsumexp(np.log(w)+norm-13*np.log(2.)-.125*v)+jac,np.log(.5)+logsumexp(np.log(aw)+an-.5*av)+jac]))
    def draw(rng):
        r=rng.rand()
        if r<.02:u=rng.rand(13)
        elif r<.50:
            j=rng.choice(len(w),p=w);u=expit(m[j]+(1. if r<.35 else 2.)*np.dot(chol[j],rng.randn(13)))
        else:
            j=rng.choice(len(aw),p=aw);u=expit(am[j]+np.dot(ach[j],rng.randn(13)))
        assert np.all((u>0)&(u<1))
        return u
    q,ok=mapped(uc[2:]); assert ok
    start,raw,status=native(q);assert status=='NATIVE_EVALUATED' and abs(start-seed['logL'])<1e-5
    rng=np.random.RandomState(81173);nprior=4096; accepted=past['support']['accepted'];assert past['support']['draws']==nprior and accepted>0
    support=accepted/float(nprior)
    result={'status':'RUNNING','model':label,'mr':mr.tolist(),'proposal_source_sha256':fit['source_sha256'],'seed_logL':start,'support':{'draws':nprior,'accepted':accepted,'fraction':support},'batches':[],'adaptive_proposal':{'means':am.tolist(),'covariances':ac.tolist(),'weights':aw.tolist(),'optimisation':opt_records},'limits':'Fixed derived static M,R conditional pilot. A native sentinel is unknown, not zero. Finite-only integral is a lower partial sum, not accepted evidence. No final EOS Bayes.'}
    def save():
        with open(out+'.tmp','w') as f:json.dump(result,f,indent=2,allow_nan=False)
        os.rename(out+'.tmp',out)
    for b in range(2):
        rng=np.random.RandomState(551031+b);rows=[];result['batches'].append({'seed':371031+b,'rows':rows})
        for i in range(1024):
            u=draw(rng);lq=logq(u);p,ok=mapped(u)
            if ok:v,raw,status=native(p)
            else:v,raw,status=None,None,'PRIOR_REJECTED'
            rows.append({'u':u.tolist(),'p':p.tolist(),'logq':lq,'logL':v,'raw_logL':raw if raw is not None and np.isfinite(raw) else None,'status':status})
            if i%16==15:save();print('F155_PROGRESS',label,b,i+1);sys.stdout.flush()
        unknown=sum(r['status'].startswith('UNRESOLVED') for r in rows)
        lw=np.array([r['logL']-r['logq'] if r['logL'] is not None else -np.inf for r in rows])
        if np.any(np.isfinite(lw)):
            ss=logsumexp(lw);ww=np.exp(lw-ss);ess=1./np.sum(ww*ww);t={'log_finite_partial_integral':float(ss-np.log(len(rows))-np.log(support)),'ess_finite':float(ess),'max_weight_fraction':float(ww.max()),'unresolved':unknown}
        else:t={'log_finite_partial_integral':None,'ess_finite':0.,'max_weight_fraction':None,'unresolved':unknown}
        result['batches'][-1]['stats']=t;save()
    a,b=[r['stats'] for r in result['batches']]
    good=all(t['unresolved']==0 and t['ess_finite']>=50 and t['max_weight_fraction']<=.1 for t in (a,b)) and abs(a['log_finite_partial_integral']-b['log_finite_partial_integral'])<=.5
    q,ok=mapped(uc[2:]); v,raw,status=native(q);assert ok and v is not None and abs(v-start)<1e-6
    result['status']='CONDITIONAL_PILOT_PASS' if good else 'CONDITIONAL_PILOT_UNCONVERGED';save()
    print('F155_COMPLETE',label,result['status'],a,b)
if __name__=='__main__':main()
