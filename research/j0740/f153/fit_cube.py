import numpy as np, hashlib, zipfile, json, sys
from pathlib import Path
from scipy.special import logit, logsumexp
from scipy.stats import truncnorm, skewnorm, multivariate_normal
from sklearn.mixture import GaussianMixture
source,out,slice_path=map(Path,sys.argv[1:]);out.mkdir(exist_ok=True,parents=True)
with zipfile.ZipFile(source) as z: raw=z.read(next(n for n in z.namelist() if n.endswith('post_equal_weights.dat')))
assert hashlib.sha256(raw).hexdigest()=='ca06332a5ee833e911e728b1fc070a84f732ccc2066387076c38533d1e3acc40'
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
fit=rng.choice(tr,15000,replace=True,p=counts[tr]/counts[tr].sum());test=rng.choice(te,10000,replace=True,p=counts[te]/counts[te].sum());center=b[fit].mean(0);scale=b[fit].std(0);x=(b[fit]-center)/scale;y=(b[test]-center)/scale
models=[];best=None
for k in (1,4,8):
 g=GaussianMixture(k,reg_covar=1e-5,random_state=42,max_iter=100,tol=.002).fit(x)
 jl=g.score_samples(y);ml=logsumexp(np.stack([np.log(w)+multivariate_normal.logpdf(y[:,:2],m[:2],c[:2,:2]) for w,m,c in zip(g.weights_,g.means_,g.covariances_)]),axis=0)
 score=float(np.mean(jl-ml));models.append(dict(k=k,conditional_holdout_log_density=score,converged=bool(g.converged_),iterations=int(g.n_iter_)));print(models[-1],flush=True)
 if g.converged_ and (best is None or score>best[0]):best=(score,g)
assert best is not None
g=best[1];result={'source_sha256':hashlib.sha256(raw).hexdigest(),'source_rows':int(counts.sum()),'unique_vectors':len(a),'train_unique':len(tr),'test_unique':len(te),'fit_rows':len(fit),'heldout_rows':len(test),'group_disjoint':not bool(set(tr)&set(te)),'models':models,'selected_components':g.n_components,'candidates':{}}
with zipfile.ZipFile(slice_path) as z:slices=json.loads(z.read('slices.json'))
result['names']=slices['parameter_names']
for r in slices['rows']:
 name=r['model']
 if name=='publisher_control' or name in result['candidates']:continue
 mr=np.array(r['p'][:2]);x0=(mr-center[:2])/scale[:2];cw=[];cm=[];cc=[]
 for wi,mi,ci in zip(g.weights_,g.means_,g.covariances_):
  A=ci[:2,:2];B=ci[2:,:2];D=ci[2:,2:];K=np.linalg.solve(A,B.T).T;cm.append(mi[2:]+K@(x0-mi[:2]));cc.append(D-K@B.T);cw.append(np.log(wi)+multivariate_normal.logpdf(x0,mi[:2],A))
 cw=np.exp(cw-logsumexp(cw));cm=np.array(cm)*scale[2:]+center[2:];cc=np.array(cc)*scale[None,2:,None]*scale[None,None,2:];assert np.min(np.linalg.eigvalsh(cc))>0
 close=(abs(a[te,0]-mr[0])<.05)&(abs(a[te,1]-mr[1])<.25)
 result['candidates'][name]={'mr':mr.tolist(),'weights':cw.tolist(),'means':cm.tolist(),'covariances':cc.tolist(),'holdout_nearby_unique':int(close.sum()),'holdout_nearby_weighted':int(counts[te][close].sum())}
result['limitations']='Conditional proposal only; duplicate physical vectors grouped before split. Chain samples not independent. No likelihood integration or evidence. WFF1 extrapolates.'
(out/'cube_proposal.json').write_text(json.dumps(result,indent=2));print('F153_FIT_COMPLETE',result['selected_components'],flush=True)
