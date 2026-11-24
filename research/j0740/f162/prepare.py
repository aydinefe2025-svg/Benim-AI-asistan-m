"""Independent Linux test of two unfinished numerical rotating witnesses.
No use of old Windows rows; exact importance densities, frozen proposals."""
import sys,json,hashlib,zipfile
from pathlib import Path
import numpy as np
from scipy.special import logit,expit,logsumexp,ndtri
from scipy.stats import truncnorm,skewnorm,multivariate_normal,qmc
from scipy.interpolate import PchipInterpolator
from sklearn.mixture import GaussianMixture
root,out=map(Path,sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
oldzip=zipfile.ZipFile(root/'old_proposal.zip')
assert hashlib.sha256((root/'old_proposal.zip').read_bytes()).hexdigest()=='b57e9abfae2a578aa4cf512562aebc3875cb9a0ec88c436fd5bb8c2b9d380503'
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
 return float(logsumexp([np.log(.02),np.log(.78)+logsumexp(np.log(w)+norm-.5*v2)+jac,np.log(.20)+logsumexp(np.log(w)+norm-13*np.log(2)-.125*v2)+jac]))
models={'MS1':('7f517332a6d391e59c043279b1deb8b103262dc5294222d3ea2b187b157fde3e','89638423d13bfbf7dc3d248a2532e51d84704872cb66f78dc1fa3ed666872214'),'MS1B':('4ea67a8519d86d2f37a84992b45f4a6fb130e76c27c39a3039bf8c0392032b96','e974c08937b98b8327d1841d1edad831853c02289f5c7022ed3e619b9b39973c')}
receipt={'status':'PROPOSAL_FROZEN','source_sha256':sha(raw),'group_disjoint':not bool(set(tr)&set(te)),'scores':scores,'components':g.n_components,'models':{}}
for label,(zh,jh) in models.items():
 rawcurve=read_zip(root/(label+'.zip'),zh,'mass_sequence_20261119.json');assert sha(rawcurve)==jh
 curve=json.loads(rawcurve);assert curve['EOS']==label and not curve['original_EOS_modified']
 stars=curve['mass_increasing_branch_C_stars'];mass=np.array([s['mass_msun'] for s in stars]);radius=np.array([s['radius_eq_km'] for s in stars]);assert np.all(np.diff(mass)>0) and len(stars)==48 and max(abs(s['spin_residual_hz']) for s in stars)<=.25
 R=PchipInterpolator(mass,radius,extrapolate=False);assert abs(R(2.073)-curve['C_sequence_reconstructed_mass_2p073_R_eq_km'])<1e-7
 # Radio prior included ONCE, via its normalized CDF. Both witnesses cover its full bounded support.
 prior=truncnorm(-5,5,loc=2.082,scale=.0703);assert mass[0]<prior.ppf(0) and mass[-1]>prior.ppf(1)
 # Piecewise constant defensive mass density in radio-CDF space.
 edges=np.linspace(0,1,513);mid=(edges[:-1]+edges[1:])/2;mm=prior.ppf(mid);rr=R(mm)
 logs=np.array([conditional(np.array([m,r]))[2]-prior.logpdf(m) for m,r in zip(mm,rr)])
 probs=.30/len(mid)+.70*np.exp(logs-logsumexp(logs));cdf=np.r_[0,np.cumsum(probs)];cdf[-1]=1
 assert abs(probs.sum()-1)<1e-12 and min(probs)*512>=.30-1e-12
 for seed in (342001,342003,342007,342011):
  # 15-dimensional randomized QMC: mass, mixture category, 13 independent normal or cube coordinates.
  pts=qmc.Sobol(15,scramble=True,seed=seed).random_base2(13);rows=[]
  for i,pt in enumerate(pts):
   j=min(511,int(np.searchsorted(cdf,pt[0],side='right')-1));assert j>=0
   um=(j+(pt[0]-cdf[j])/probs[j])/512
   M=float(prior.ppf(um));rad=float(R(M));w,means,_=conditional(np.array([M,rad]))
   mix=pt[1];v=pt[2:]
   if mix<.02:uu=v.copy()
   else:
    f=(mix-.02)/.78 if mix<.80 else (mix-.80)/.20
    l=min(len(w)-1,int(np.searchsorted(np.cumsum(w),f,side='right')))
    uu=expit(means[l]+(1 if mix<.80 else 2)*chol[l]@ndtri(v))
   assert np.all((uu>0)&(uu<1)) and np.isfinite(rad)
   rows.append(dict(index=i,mass=M,radius=rad,mass_u=float(um),u=uu.tolist(),logq_mass=float(np.log(probs[j]*512)),logq_nuisance=logq(uu,w,means),phase_positive=bool(uu[2]>.5)))
  previous=json.loads(oldzip.read('%s_%d.json'%(label,seed)))
  assert previous['model']==label and previous['seed']==seed and len(previous['rows'])==2048
  for old,new in zip(previous['rows'],rows[:2048]):
   assert old['index']==new['index'] and old['phase_positive']==new['phase_positive']
   for key in ('mass','radius','mass_u','logq_mass','logq_nuisance','u'):
    assert np.allclose(old[key],new[key],rtol=0,atol=1e-9),(label,seed,old['index'],key)
  # Retain byte-identical old prefix in original artifact. Only new suffix is emitted.
  p=out/('%s_%d.json'%(label,seed));p.write_text(json.dumps(dict(model=label,seed=seed,curve_sha256=jh,support=.24947354926879406,rows=rows[2048:],old_proposal_sha256=sha(oldzip.read('%s_%d.json'%(label,seed))),prefix_verified=2048),allow_nan=False))
  print('F162_PREFIX_VERIFIED',label,seed,2048,flush=True)
  print('F161_FROZEN',label,seed,sha(p.read_bytes()),flush=True)
 receipt['models'][label]={'curve_sha256':jh,'mass_range':mass[[0,-1]].tolist(),'radio_prior_covered':True,'mass_density_min':float(min(probs)*512),'mass_density_max':float(max(probs)*512),'radius_at_2p073':float(R(2.073))}
(out/'fit_receipt.json').write_text(json.dumps(receipt,indent=2));print('F161_PREP_COMPLETE',flush=True)
