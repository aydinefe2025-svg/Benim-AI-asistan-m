from __future__ import print_function,division
import os,sys,json,types
import numpy as np
from scipy.special import expit,logit,logsumexp
from scipy.stats import multivariate_normal
import xpsi
from conditional import forward
def main():
    config,slices,proposal,out,label,pilot_path=sys.argv[1:]
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
        os.environ['F156_BYPASS_CUTOFF']='1'
        v=float(L(p,force=True))
        if not np.isfinite(v) or v< -1e50:return None,v,'UNRESOLVED_NATIVE_SENTINEL'
        ds=[float(x.loglikelihood) for grp in L._signals for x in grp]
        if len(ds)!=4 or not np.all(np.isfinite(ds)) or abs(sum(ds)-v)>1e-5:
            return None,v,'UNRESOLVED_DETECTOR_SUM'
        return v,v,'NATIVE_EVALUATED'
    # F155 is training data only. Use local Hessian curvature of the native
    # log-density in whitened logit coordinates, with bounded eigenvalues.
    # Student t tails plus the old proposal and uniform cube ensure support.
    from scipy.optimize import minimize
    from scipy.special import gammaln
    past=json.load(open(pilot_path))
    assert past['model']==label and past['status']=='CONDITIONAL_PILOT_UNCONVERGED'
    rows=[r for batch in past['batches'] for r in batch['rows']]
    assert len(rows)==2048 and not any(r['status'].startswith('UNRESOLVED') for r in rows)
    finite=[r for r in rows if r['logL'] is not None]
    y=np.array([logit(r['u']) for r in finite]);lw=np.array([r['logL']-r['logq'] for r in finite])
    oldp=past['adaptive_proposal'];om=np.array(oldp['means']);oc=np.array(oldp['covariances']);ow=np.array(oldp['weights'])
    och=np.linalg.cholesky(oc);oi=np.linalg.inv(oc);on=-.5*(13*np.log(2*np.pi)+np.linalg.slogdet(oc)[1])
    order=np.argsort(lw)[::-1];anchors=[]
    for i in order:
        z=y[i];delta=z-om;j=int(np.argmax(np.log(ow)+on-.5*np.einsum('ki,kij,kj->k',delta,oi,delta)))
        if all(np.linalg.norm(np.linalg.solve(och[j],z-t[0]))>2.5 for t in anchors):
            anchors.append((z,j))
        if len(anchors)>=2:break
    assert len(anchors)==2
    records=[]; centres=[]; covs=[]
    for k,(z,j) in enumerate(anchors):
        count=[0]
        def objective(t):
            count[0]+=1
            u=expit(z+np.dot(och[j],t))
            if np.any(u<=0.) or np.any(u>=1.):return 1e50
            pp,ok=mapped(u)
            if not ok:return 1e50
            v,raw,status=native(pp)
            if v is None:return 1e50
            return -v-np.sum(np.log(u)+np.log1p(-u))
        base=objective(np.zeros(13))
        opt=minimize(objective,np.zeros(13),method='Powell',options={'maxfev':600,'xtol':.01,'ftol':1e-9})
        x=opt.x if opt.fun<base else np.zeros(13)
        f0=objective(x)
        h=.15;E=np.eye(13)*h;H=np.zeros((13,13));invalid=0
        for i in range(13):
            v1=objective(x+E[i]);v2=objective(x-E[i])
            if max(v1,v2)>1e40:invalid+=1;H[i,i]=1.
            else:H[i,i]=(v1+v2-2*f0)/(h*h)
            for jj in range(i):
                vals=[objective(x+E[i]+E[jj]),objective(x+E[i]-E[jj]),objective(x-E[i]+E[jj]),objective(x-E[i]-E[jj])]
                if max(vals)>1e40:invalid+=1
                else:H[i,jj]=H[jj,i]=(vals[0]-vals[1]-vals[2]+vals[3])/(4*h*h)
        ev,V=np.linalg.eigh(H)
        # If local prior boundary invalidates the stencil, retain original
        # covariance rather than claiming a valid Hessian.
        if invalid:cov=oc[j]
        else:
            Hinv=np.dot(V/np.clip(ev,.2,100.),V.T)
            cov=np.dot(och[j],np.dot(Hinv,och[j].T))
        centre=z+np.dot(och[j],x);assert np.min(np.linalg.eigvalsh(cov))>0
        centres.append(centre);covs.append(cov)
        records.append({'anchor':k,'objective_before':float(base),'objective_after':float(f0),'native_objective_calls':count[0],'raw_eigenvalues':ev.tolist(),'invalid_stencils':invalid,'used_hessian':not bool(invalid)})
        print('F156_CURVATURE',label,k,records[-1]);sys.stdout.flush()
    am=np.array(centres);ac=np.array(covs);aw=np.ones(len(am))/len(am);ach=np.linalg.cholesky(ac);ai=np.linalg.inv(ac)
    # multivariate Student t with nu=5 in 13 dimensions, normalized.
    nu=5.;dim=13
    an=gammaln((nu+dim)/2)-gammaln(nu/2)-dim/2*np.log(nu*np.pi)-.5*np.linalg.slogdet(ac)[1]
    def logq(u):
        yy=logit(u);d=yy-om;ov=np.einsum('ki,kij,kj->k',d,oi,d);jac=-np.sum(np.log(u)+np.log1p(-u))
        d=yy-am;av=np.einsum('ki,kij,kj->k',d,ai,d)
        d=yy-m;v=np.einsum('ki,kij,kj->k',d,inv,d)
        return float(logsumexp([np.log(.02),np.log(.18)+logsumexp(np.log(w)+norm-.5*v)+jac,np.log(.30)+logsumexp(np.log(ow)+on-.5*ov)+jac,np.log(.50)+logsumexp(np.log(aw)+an-(nu+dim)/2*np.log1p(av/nu))+jac]))
    def draw(rng):
        r=rng.rand()
        if r<.02:u=rng.rand(13)
        elif r<.20:
            j=rng.choice(len(w),p=w);u=expit(m[j]+np.dot(chol[j],rng.randn(13)))
        elif r<.50:
            j=rng.choice(len(ow),p=ow);u=expit(om[j]+np.dot(och[j],rng.randn(13)))
        else:
            j=rng.choice(len(aw),p=aw);u=expit(am[j]+np.dot(ach[j],rng.randn(13))*np.sqrt(nu/rng.chisquare(nu)))
        assert np.all((u>0)&(u<1))
        return u
    q,ok=mapped(uc[2:]); assert ok
    start,raw,status=native(q);assert status=='NATIVE_EVALUATED' and abs(start-seed['logL'])<1e-5
    rng=np.random.RandomState(81173);nprior=4096; accepted=past['support']['accepted'];assert past['support']['draws']==nprior and accepted>0
    support=accepted/float(nprior)
    result={'status':'RUNNING','model':label,'mr':mr.tolist(),'proposal_source_sha256':fit['source_sha256'],'seed_logL':start,'support':{'draws':nprior,'accepted':accepted,'fraction':support},'batches':[],'adaptive_proposal':{'means':am.tolist(),'covariances':ac.tolist(),'weights':aw.tolist(),'optimisation':records,'student_t_df':nu},'limits':'Fixed derived static M,R conditional pilot. A native sentinel is unknown, not zero. Finite-only integral is a lower partial sum, not accepted evidence. No final EOS Bayes.'}
    def save():
        with open(out+'.tmp','w') as f:json.dump(result,f,indent=2,allow_nan=False)
        os.rename(out+'.tmp',out)
    for b in range(2):
        rng=np.random.RandomState(661031+b);rows=[];result['batches'].append({'seed':661031+b,'rows':rows})
        for i in range(2048):
            u=draw(rng);lq=logq(u);p,ok=mapped(u)
            if ok:v,raw,status=native(p)
            else:v,raw,status=None,None,'PRIOR_REJECTED'
            rows.append({'u':u.tolist(),'p':p.tolist(),'logq':lq,'logL':v,'raw_logL':raw if raw is not None and np.isfinite(raw) else None,'status':status})
            if i%16==15:save();print('F156_PROGRESS',label,b,i+1);sys.stdout.flush()
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
    print('F156_COMPLETE',label,result['status'],a,b)
if __name__=='__main__':main()
