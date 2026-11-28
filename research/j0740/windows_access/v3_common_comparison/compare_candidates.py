"""J0740 v3 candidate head-to-head benchmark on COMMON synthetic targets.
No native X-PSI, no held-out J0740, no source/prior modifications.
This comparison does not establish EOS inference or real-data convergence.
"""
import json, math, hashlib, sys, pathlib, importlib.util
import numpy as np
from scipy.special import logsumexp, ndtri, ndtr
from scipy.stats import qmc

ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'bounded'))
import support_aware_mixture as bounded
spec=importlib.util.spec_from_file_location('defensive_latent_v3',(ROOT/'latent'/'defensive_latent_v3.py'))
latent=importlib.util.module_from_spec(spec)
spec.loader.exec_module(latent)
D=13
LOG2PI=math.log(2*math.pi)
TRAIN_SEED=40017
SEEDS=[40021,40023,40027,40031]
NTRAIN=4096
NTEST=1024

class UnitBase:
    def from_unit(self,u):
        a=np.asarray(u)
        if a.ndim !=2 or a.shape[1]<13 or np.any((a[:,:13]<=0)|(a[:,:13]>=1)):
            raise ValueError('base unit coordinates must be in (0,1)^13')
        return ndtri(a[:,:13])
    def logpdf(self,z):
        z=np.asarray(z)
        return -.5*np.sum(z*z,axis=1)-.5*D*LOG2PI

base=UnitBase()

def gauss(z,mu,cov):
    L=np.linalg.cholesky(cov)
    a=np.linalg.solve(L,(z-mu).T).T
    return -.5*D*LOG2PI - np.log(np.diag(L)).sum() -.5*np.sum(a*a,axis=1)

def make_target(kind):
    mu=np.zeros(D)
    if kind=='shifted':
        mu[:2]=[1.2,-.8]; cov=np.eye(D)
        return lambda z:gauss(z,mu,cov)
    if kind=='correlated':
        mu[:2]=[.5,-.5]; cov=np.eye(D)
        cov[2,3]=cov[3,2]=.87
        cov[5,6]=cov[6,5]=-.78
        return lambda z:gauss(z,mu,cov)
    if kind=='bimodal-phase':
        mu1=mu.copy();mu2=mu.copy();mu1[[2,4]]=[1.25,-1.25];mu2[[2,4]]=[-1.25,1.25]
        cov=np.eye(D);cov[2,2]=.8;cov[4,4]=.8
        return lambda z:logsumexp(np.vstack([gauss(z,mu1,cov),gauss(z,mu2,cov)]),axis=0)-math.log(2)
    if kind=='diffuse':
        cov=np.eye(D)*1.3
        return lambda z:gauss(z,mu,cov)
    raise ValueError(kind)

def importance(logp,logq):
    l=logp-logq
    norm=logsumexp(l)
    w=np.exp(l-norm)
    return dict(ess=float(1/(w@w)),max_weight=float(np.max(w)),logZ=float(norm-math.log(len(l))),cdf_endpoints=int(np.count_nonzero(np.any((ndtr(z_global)<=0)|(ndtr(z_global)>=1),axis=1))))

def from_unit_latent(model,u):
    assignment=np.searchsorted(np.cumsum(model.fractions),u[:,0],side='right')
    if np.any(assignment==3):raise ValueError('categorical endpoint')
    normal=ndtri(u[:,1:14]);z=np.empty((len(u),D));
    for i in range(3):
        mask=assignment==i
        if i==0:z[mask]=normal[mask]
        if i==1:z[mask]=normal[mask]@model.chol.T+model.mean
        if i==2:z[mask]=normal[mask]@model.tail_chol.T+model.mean
    return z

report={
 'kind':'SYNTHETIC_COMMON_TARGET_COMPARISON_NO_REAL_XPSI',
 'targets':['shifted','correlated','bimodal-phase','diffuse'],
 'N_train':NTRAIN,'N_test_per_seed':NTEST,
 'train_seed':TRAIN_SEED,'test_seeds':SEEDS,
 'samples_kept':True,'real_photon_calls':0,
 'full_MR_convergence':'NOT_ESTABLISHED','EOS_Bayes':'NOT_RUN',
 'results':[]
}
for target in report['targets']:
    p=make_target(target)
    ztrain=ndtri(qmc.Sobol(d=13,scramble=True,seed=TRAIN_SEED+sum(map(ord,target))).random_base2(int(math.log2(NTRAIN))))
    train_lw=p(ztrain)-base.logpdf(ztrain)
    esstrain=float(math.exp(2*logsumexp(train_lw)-logsumexp(2*train_lw)))
    result={'target':target,'training_ESS':esstrain,'seeds':[]}
    models={}
    try:
        models['bounded'],_=bounded.fit_training_only(ztrain,train_lw,base,model_sha256='SYNTHETIC_TEST_ONLY')
    except Exception as e:
        result['bounded_fit_fail_closed']=str(e)
    try:
        models['latent'],_=latent.fit_training_only(ztrain,train_lw)
    except Exception as e:
        result['latent_fit_fail_closed']=str(e)
    # Holdout never used to fit/tune. All methods draw from same scrambled Sobol matrices.
    for seed in SEEDS:
        u=qmc.Sobol(d=17,scramble=True,seed=seed).random_base2(int(math.log2(NTEST)))
        trial={'seed':seed}
        for method in ['base','bounded','latent']:
            if method not in models and method!='base':continue
            if method=='base':z=base.from_unit(u[:,1:]) ; lq=base.logpdf(z)
            elif method=='bounded':z=models['bounded'].from_unit(u);lq=models['bounded'].logpdf(z)
            else:z=from_unit_latent(models['latent'],u);lq=models['latent'].logpdf(z)
            z_global=z
            lp=p(z)
            if not(np.isfinite(lp).all() and np.isfinite(lq).all() and np.isfinite(z).all()):
                raise ValueError('non-finite density at method '+method)
            # Calculate analytically normalized p vs q; logZ should be near zero.
            met=importance(lp,lq)
            trial[method]=met
        result['seeds'].append(trial)
    report['results'].append(result)

# Aggregate only predefined 4 seeds, not cherry picking.
for item in report['results']:
    item['summary']={}
    for method in ['base','bounded','latent']:
        have=[seed[method] for seed in item['seeds'] if method in seed]
        if have:
            item['summary'][method]={
              'mean_ESS':float(np.mean([m['ess'] for m in have])),
              'worst_max_weight':max(m['max_weight'] for m in have),
              'max_abs_logZ_error':max(abs(m['logZ']) for m in have),
              'total_cdf_endpoint_rows':sum(m['cdf_endpoints'] for m in have)
            }
print(json.dumps({r['target']:{'trainESS':r['training_ESS'],**r['summary']} for r in report['results']},indent=2))
output=ROOT/'candidate_comparison_synthetic.json'
with output.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
print('REPORT_PATH',output)
print('REPORT_SHA256',hashlib.sha256(output.read_bytes()).hexdigest())
