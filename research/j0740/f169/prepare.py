"""F168: fresh independent two-model rebalanced proposal. 2% uniform, 58% narrow, 40% scale-1.5. No previous native rows used in new estimator."""
import sys,json,hashlib,zipfile
from pathlib import Path
import numpy as np
from scipy.special import logit,expit,logsumexp,ndtri
from scipy.stats import truncnorm,skewnorm,multivariate_normal,qmc
from scipy.interpolate import PchipInterpolator
from sklearn.mixture import GaussianMixture
root,out=map(Path,sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
def read_zip(p,expected,member):
 assert sha(p.read_bytes())==expected,p
 with zipfile.ZipFile(p) as z:
  assert z.testzip() is None
  return z.read(next(n for n in z.namelist() if n.endswith(member)))
raw=read_zip(root/'chain.zip','c89cd81f2ade68ee17004838017869a6e8a9e1d2bd5f484f08601495fea82532','post_equal_weights.dat')
assert sha(raw)=='ca06332a5ee833e911e728b1fc070a84f732ccc2066387076c38533d1e3acc40'
a=np.loadtxt(raw.splitlines());assert a.shape==(379669,16)
a,counts=np.unique(a[:,:15],axis=0,return_counts=True)
u=np.empty((len(a),13));u[:,0]=skewnorm.cdf(a[:,2],1.7,loc=1.002,scale=.227)
mu=.0427+.8*.00304/.0703*(a[:,0]-2.082);sd=.00304*np.sqrt(1-.8**2)
u[:,1]=truncnorm.cdf(a[:,3],np.minimum(-10,(-1-mu)/sd),10,loc=mu,scale=sd)
for j in (4,8):u[:,j-2]=a[:,j]+.5
for j in (5,9):u[:,j-2]=(np.cos(a[:,j])-np.cos(np.pi-.001))/(np.cos(.001)-np.cos(np.pi-.001))
for j in (6,10):u[:,j-2]=(a[:,j]-.001)/(np.pi/2-.002)
for j in (7,11):u[:,j-2]=(a[:,j]-5.1)/1.7
u[:,10]=truncnorm.cdf(a[:,12],-5,5,loc=1,scale=.104);u[:,11]=a[:,13]/10
u[:,12]=truncnorm.cdf(a[:,14],-5,5,loc=1+.916*(a[:,12]-1),scale=.104*np.sqrt(1-.916**2))
assert np.all((u>0)&(u<1))
b=np.c_[a[:,:2],logit(u)];rng=np.random.default_rng(20261124);ids=rng.permutation(len(a));n=int(.8*len(ids));tr,te=ids[:n],ids[n:]
fit=rng.choice(tr,40000,replace=True,p=counts[tr]/counts[tr].sum());test=rng.choice(te,15000,replace=True,p=counts[te]/counts[te].sum());center=b[fit].mean(0);scale=b[fit].std(0);x=(b[fit]-center)/scale;y=(b[test]-center)/scale
scores=[];best=None
for k in (8,16,24):
 g=GaussianMixture(k,reg_covar=1e-5,random_state=42,max_iter=150,tol=.001).fit(x)
 jl=g.score_samples(y);ml=logsumexp(np.stack([np.log(w)+multivariate_normal.logpdf(y[:,:2],m[:2],c[:2,:2]) for w,m,c in zip(g.weights_,g.means_,g.covariances_)]),axis=0)
 score=float(np.mean(jl-ml));scores.append(dict(k=k,conditional_holdout_log_density=score,converged=bool(g.converged_),iterations=int(g.n_iter_)));print(scores[-1],flush=True)
 if g.converged_ and (best is None or score>best[0]):best=(score,g)
assert best is not None
g=best[1]
# Convert each joint Gaussian to exact conditional normal parameters.
K=[];C=[]
for c in g.covariances_:
 A=c[:2,:2];B=c[2:,:2];D=c[2:,2:];kk=np.linalg.solve(A,B.T).T;K.append(kk);C.append((D-kk@B.T)*scale[None,2:]*scale[2:,None])
K=np.array(K);C=np.array(C);assert np.min(np.linalg.eigvalsh(C))>0
chol=np.linalg.cholesky(C);inv=np.linalg.inv(C);norm=-.5*(13*np.log(2*np.pi)+np.linalg.slogdet(C)[1])
def conditional(mr):
 x0=(mr-center[:2])/scale[:2];dd=x0-g.means_[:,:2];means=(g.means_[:,2:]+np.einsum('kij,kj->ki',K,dd))*scale[2:]+center[2:]
 lw=np.array([np.log(w)+multivariate_normal.logpdf(x0,m[:2],c[:2,:2]) for w,m,c in zip(g.weights_,g.means_,g.covariances_)])
 return np.exp(lw-logsumexp(lw)),means,float(logsumexp(lw))
def logq(v,w,m):
 z=logit(v);d=z-m;v2=np.einsum('ki,kij,kj->k',d,inv,d)
 jac=-np.sum(np.log(v)+np.log1p(-v))
 return float(logsumexp([np.log(.02),np.log(.58)+logsumexp(np.log(w)+norm-.5*v2)+jac,np.log(.40)+logsumexp(np.log(w)+norm-13*np.log(1.5)-.5*v2/(1.5**2))+jac]))
models={'ENG':'cc1b4e189692731c9169e7ef2914a58267dabacae59edf9b190576be04fd3a5e','MPA1':'f9792b3d0a6d38faf5ac564f2f09900ae73aadf534ab5ad6c8ebe9268fe47a18','MS1':'f7b9696be96985d86038b6a9f652d825328983270edb67bd521f4dbbfdec4bd3','MS1B':'1b3302ae22ec13333e8e38c86ca019c0bc2723242b3d5861a2d518d45c6324a0','WFF1':'85de083d995c25816a01f64df15d2a69cb4298cc42c2cc88da02c201347a3f33','WFF2':'df7459c491a32d9b2eff152e927b123e77fc3eeeca5c62e6ba2a32c043e8d08d','APR4_CAUSAL':'2c12790459c62c3d758dcbe8e3a425cec6f8328dec3c6701af28e1ca13a96d5c'}
models={k:v for k,v in models.items() if k == 'MS1'}
receipt={'status':'PROPOSAL_FROZEN','source_sha256':sha(raw),'group_disjoint':not bool(set(tr)&set(te)),'scores':scores,'components':g.n_components,'models':{},'scope':'Six F164 derived majorants, distinct F39 APR4 causal completion; first sampled rising mass branch only'}
for label,zh in models.items():
 member='J0740_APR4_FIXED_FREQUENCY_CURVE_F38_INTEGRAL.json' if label=='APR4_CAUSAL' else 'result.json'
 rawcurve=read_zip(root/(label+'.zip'),zh,member);jh=sha(rawcurve);curve=json.loads(rawcurve)
 if label=='APR4_CAUSAL':
  assert curve['fixed_frequency_roots_success']==165 and not curve['fixed_frequency_roots_failures'] and curve['target_spin_hz']==346.536369
  stars=curve['central_density_sweep'];mass=np.array([q['mass_msun'] for q in stars])*6.673e-8*1.989e33/1.3271244e26;radius=np.array([q['radius_eq_km'] for q in stars]);assert max(abs(q['spin_hz']-346.536369) for q in stars)<.001
  k=int(np.flatnonzero(np.diff(mass)<=0)[0])+1;assert k==138;mass=mass[:k];radius=radius[:k]
 else:
  assert curve['status']=='NATIVE_EQUILIBRIA_RECORDED' and curve['inputs']['model']==label and curve['inputs']['grid']=='201x401'
  stars=curve['scan'];k=int(np.argmax([q['M_msun'] for q in stars]));stars=stars[:k+1];assert all(q['rho']>stars[-1]['rho'] for q in curve['scan_errors'])
  stars=sorted(stars+[curve['target']],key=lambda q:q['M_msun']);mass=np.array([q['M_msun'] for q in stars]);radius=np.array([q['R_km'] for q in stars]);assert max(abs(q['f']-346.536369) for q in stars)<=.05
 assert np.all(np.diff(mass)>0)
 R=PchipInterpolator(mass,radius,extrapolate=False)
 prior=truncnorm(-5,5,loc=2.082,scale=.0703);ulo=float(prior.cdf(mass[0]));uhi=float(prior.cdf(mass[-1]));frac=uhi-ulo;assert .70<frac<=1.0
 # Density in FULL normalized radio-prior CDF. Missing branch contributes zero.
 edges=np.linspace(0,1,513);mid=(edges[:-1]+edges[1:])/2;mm=prior.ppf(ulo+frac*mid);rr=R(mm)
 logs=np.array([conditional(np.array([m,r]))[2]-prior.logpdf(m) for m,r in zip(mm,rr)])
 probs=.30/len(mid)+.70*np.exp(logs-logsumexp(logs));cdf=np.r_[0,np.cumsum(probs)];cdf[-1]=1
 assert abs(probs.sum()-1)<1e-12 and min(probs)*512>=.30-1e-12
 for seed in (368001,368003,368007,368011):
  # 15-dimensional randomized QMC: mass, mixture category, 13 independent normal or cube coordinates.
  pts=qmc.Sobol(15,scramble=True,seed=seed).random_base2(15);rows=[]
  for i,pt in enumerate(pts):
   j=min(511,int(np.searchsorted(cdf,pt[0],side='right')-1));assert j>=0
   um=ulo+frac*(j+(pt[0]-cdf[j])/probs[j])/512
   M=float(prior.ppf(um));rad=float(R(M));w,means,_=conditional(np.array([M,rad]))
   mix=pt[1];v=pt[2:]
   if mix<.02:uu=v.copy()
   else:
    f=(mix-.02)/.58 if mix<.60 else (mix-.60)/.40
    l=min(len(w)-1,int(np.searchsorted(np.cumsum(w),f,side='right')))
    uu=expit(means[l]+(1 if mix<.60 else 1.5)*chol[l]@ndtri(v))
   assert np.all((uu>0)&(uu<1)) and np.isfinite(rad)
   rows.append(dict(index=i,mass=M,radius=rad,mass_u=float(um),u=uu.tolist(),logq_mass=float(np.log(probs[j]*512/frac)),logq_nuisance=logq(uu,w,means),phase_positive=bool(uu[2]>.5)))
  p=out/('%s_%d.json'%(label,seed));p.write_text(json.dumps(dict(model=label,seed=seed,curve_sha256=jh,mass_fraction=frac,curve_zip_sha=zh,support=.24947354926879406,rows=rows),allow_nan=False))
  print('F168_FROZEN',label,seed,sha(p.read_bytes()),flush=True)
 receipt['models'][label]={'curve_sha256':jh,'mass_range':mass[[0,-1]].tolist(),'radio_prior_fraction':frac,'curve_zip_sha':zh,'mass_density_min':float(min(probs)*512),'mass_density_max':float(max(probs)*512),'radius_at_2p073':float(R(2.073))}
(out/'fit_receipt.json').write_text(json.dumps(receipt,indent=2));print('F168_PREP_COMPLETE',flush=True)
