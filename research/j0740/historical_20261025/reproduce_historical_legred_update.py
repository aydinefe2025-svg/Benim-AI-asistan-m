import argparse,hashlib,json,tarfile
from pathlib import Path
import numpy as np,h5py
from scipy.ndimage import gaussian_filter,map_coordinates
from scipy.signal import savgol_filter
base=Path(__file__).resolve().parent / 'inputs'
def lognorm(m,mu,sd):return -.5*((m-mu)/sd)**2-np.log(sd*np.sqrt(2*np.pi))
def weighted_stats(x,w):
 s=w.sum();mu=np.sum(w*x)/s;sd=np.sqrt(np.sum(w*(x-mu)**2)/s);return float(mu),float(sd)
def weighted_quantiles(x,w,qs=(.16,.5,.84)):
 ix=np.argsort(x);xx=np.asarray(x)[ix];ww=np.asarray(w)[ix];cc=np.cumsum(ww)/ww.sum();return [float(np.interp(q,cc,xx)) for q in qs]
# New Salmi 2024 posterior samples: equal-weight, mass prior N(2.082,0.0703), flat radius.
with tarfile.open(base/'mr_samples_and_contours.tar.gz','r:gz') as tf:
 candidates=[x for x in tf.getmembers() if x.name.endswith('J0740_gamma_NxX_lp40k_se001_mrsamples_post_equal_weights.dat')]
 if len(candidates)!=1:raise ValueError('SALMI_EQUAL_WEIGHT_MEMBER_MISSING_OR_AMBIGUOUS')
 new_samples=np.loadtxt(tf.extractfile(candidates[0]),dtype=np.float64,ndmin=2)
 if new_samples.shape!=(379669,2):raise ValueError('SALMI_SAMPLE_SHAPE:'+str(new_samples.shape))
mn,rn=new_samples[:,0],new_samples[:,1]
wn=np.exp(lognorm(mn,2.08,.07)-lognorm(mn,2.082,.0703))
# Old Miller 2021 source posterior: retain original per-row nested-sampling weight, then prior-transform.
old_data=np.loadtxt(base/'NICER+XMM_J0740_full.txt',comments='#')
mo,ro,wraw=old_data[:,1],old_data[:,0],old_data[:,-1]
wo=wraw*np.exp(lognorm(mo,2.08,.07)-lognorm(mo,2.08,.09))*ro**2/mo
# weighted sample moments for separate standardized grids
muMn,sdMn=weighted_stats(mn,wn);muRn,sdRn=weighted_stats(rn,wn)
muMo,sdMo=weighted_stats(mo,wo);muRo,sdRo=weighted_stats(ro,wo)
def build_grid(m,r,w,mum,sdm,mur,sdr,nb=280):
 zm=(m-mum)/sdm;zr=(r-mur)/sdr
 em=np.linspace(zm.min()-.3,zm.max()+.3,nb+1);er=np.linspace(zr.min()-.3,zr.max()+.3,nb+1)
 dzm=em[1]-em[0];dzr=er[1]-er[0]
 H,_,_=np.histogram2d(zm,zr,bins=(em,er),weights=w,density=True)
 return H,em,er,dzm,dzr,mum,sdm,mur,sdr
def smooth_grid(grid,bw):
 H,em,er,dzm,dzr,mum,sdm,mur,sdr=grid
 X=gaussian_filter(H,sigma=(bw/dzm,bw/dzr),mode='constant');X/=X.sum()*dzm*dzr
 return (X,em,er,dzm,dzr,mum,sdm,mur,sdr)
def eval_grid(grid,m,r):
 X,em,er,dzm,dzr,mum,sdm,mur,sdr=grid
 m=np.asarray(m);r=np.asarray(r)
 c=np.vstack([(((m-mum)/sdm-em[0])/dzm-.5).ravel(),(((r-mur)/sdr-er[0])/dzr-.5).ravel()])
 return (map_coordinates(X,c,order=1,mode='constant',cval=0,prefilter=False)/(sdm*sdr)).reshape(m.shape)
old_base=build_grid(mo,ro,wo,muMo,sdMo,muRo,sdRo)
new_base=build_grid(mn,rn,wn,muMn,sdMn,muRn,sdRn)
bws=[.12,.16,.20]
old_grids={bw:smooth_grid(old_base,bw) for bw in bws}
new_grids={bw:smooth_grid(new_base,bw) for bw in bws}
mass_grid=np.arange(1.75,2.45+0.0025,.005);nM=len(mass_grid);batch_eos=500;max_branches=2
with h5py.File(base/'LCEHL_EOS_posterior_samples_PSR+GW+NICER.h5','r') as f:
 keys=sorted(f['ns'].keys(),key=lambda z:int(z.split('_')[1]));n=len(keys)
 radius_grid=np.full((n,max_branches,nM),np.nan,dtype=np.float32)
 mmax=np.full(n,np.nan);r14=np.full(n,np.nan);lam14=np.full(n,np.nan);r2073=np.full(n,np.nan);branches_count=np.zeros(n,int)
 for j,k in enumerate(keys):
  a=f['ns'][k][:];rho=a['rhoc'];m=a['M'];r=a['R'];la=a['Lambda']
  good=np.isfinite(rho)&np.isfinite(m)&np.isfinite(r)&np.isfinite(la);rho,m,r,la=rho[good],m[good],r[good],la[good]
  if len(m)<7:continue
  mmax[j]=float(np.max(m));ms=savgol_filter(m,7,2,mode='interp')
  ids=np.where(np.diff(ms)>0)[0];starts=[];ends=[]
  if len(ids):
   st=pr=int(ids[0])
   for xx in ids[1:]:
    xx=int(xx)
    if xx>pr+1:starts.append(st);ends.append(pr+1);st=xx
    pr=xx
   starts.append(st);ends.append(pr+1)
  branches=[]
  for st,en in zip(starts,ends):
   if en-st+1<5:continue
   mm=ms[st:en+1];rr=r[st:en+1];ll=la[st:en+1];keep=np.r_[True,np.diff(mm)>0];mm,rr,ll=mm[keep],rr[keep],ll[keep]
   if len(mm)>=4:branches.append((mm,rr,ll))
  sup=[b for b in branches if min(2.45,b[0][-1])>max(1.75,b[0][0])]
  branches_count[j]=len(sup)
  for bi,(mm,rr,ll) in enumerate(sup[:max_branches]):
   mask=(mass_grid>=mm[0])&(mass_grid<=mm[-1]);radius_grid[j,bi,mask]=np.interp(mass_grid[mask],mm,rr)
  for mm,rr,ll in branches:
   if not np.isfinite(r14[j]) and mm[0]<=1.4<=mm[-1]:r14[j]=np.interp(1.4,mm,rr);lam14[j]=np.interp(1.4,mm,ll)
   if not np.isfinite(r2073[j]) and mm[0]<=2.073<=mm[-1]:r2073[j]=np.interp(2.073,mm,rr)
# Independent reproduction of the historical KDE-to-KDE primary result; no second source likelihood is multiplied.
keys_weights={f'KDE_new_bw={bn}|KDE_old_bw={bo}|offset={off}':np.zeros(n) for bn in bws for bo in bws for off in [0.0,1.0]}
for start in range(0,n,batch_eos):
 end=start+batch_eos;rg=radius_grid[start:end];mg=np.broadcast_to(mass_grid,(end-start,max_branches,nM));valid0=np.isfinite(rg)
 for off in [0.0,1.0]:
  valid=valid0&(rg>3*1.47662504*mg+off)&(rg<16.)
  for bn in bws:
   qnew=np.where(valid,eval_grid(new_grids[bn],mg,rg),0.)
   znew=np.trapezoid(qnew,mass_grid,axis=2).sum(axis=1)
   for bo in bws:
    qold=np.where(valid,eval_grid(old_grids[bo],mg,rg),0.)
    zold=np.trapezoid(qold,mass_grid,axis=2).sum(axis=1)
    keys_weights[f'KDE_new_bw={bn}|KDE_old_bw={bo}|offset={off}'][start:end]=np.divide(znew,zold,out=np.zeros_like(znew),where=zold>1e-200)
def quant(v,w):
 v=np.asarray(v);w=np.asarray(w);ok=np.isfinite(v)&np.isfinite(w)&(w>0);v,w=v[ok],w[ok]
 if not len(v):return [None]*3
 ix=np.argsort(v);v,w=v[ix],w[ix];c=np.cumsum(w)/w.sum()
 return [float(np.interp(t,c,v)) for t in [.16,.5,.84]]
def ess(w):
 w=w[np.isfinite(w)&(w>0)]
 return float(w.sum()**2/(w@w)) if len(w) else 0.
out={'method':'Replace old J0740 NICER likelihood in Legred PSR+GW+NICER EOS posterior using ratio of mass-integrated new/old source posterior densities under a common source prior. Crucially, original 1,600,920-row Miller source file posterior weights (column 13) are included before transforming mass prior and compactness prior. New Salmi samples are equal-weight; new flow and weighted KDE are compared.','base':'Legred PSR+GW+NICER EOS ensemble, 10,000 EOS draws; retains J0030 NICER, J0348 radio, GW170817/GW190425; replaces old J0740 NICER with Salmi 2024.','old_raw_samples':int(len(mo)),'old_raw_weight_sum':float(wraw.sum()),'old_raw_weight_ESS':float(wraw.sum()**2/(wraw@wraw)),'old_prior_corrected_weight_ESS':float(wo.sum()**2/(wo@wo)),'old_corrected_mass_weighted_q16_50_84':weighted_quantiles(mo,wo),'old_corrected_radius_weighted_q16_50_84':weighted_quantiles(ro,wo),'new_samples':int(len(mn)),'new_prior_alignment_weight_ESS':float(wn.sum()**2/(wn@wn)),'old_corrected_weighted_mean_M_R':[muMo,muRo],'old_corrected_weighted_std_M_R':[sdMo,sdRo],'new_aligned_weighted_mean_M_R':weighted_stats(mn,wn)[:1]+weighted_stats(rn,wn)[:1],'EOS_count':n,'branches_in_mass_support':int(branches_count.sum()),'EOS_with_multiple_branches':int((branches_count>1).sum()),'mass_grid_Msun':[1.75,2.45,.005],'metrics':{}}
for tag,w in keys_weights.items():
 out['metrics'][tag]={'ESS':ess(w),'R14_km':quant(r14,w),'Lambda14':quant(lam14,w),'R_at_2.073_km':quant(r2073,w),'Mmax_Msun':quant(mmax,w),'nonzero':int(np.sum(w>0))}
# Hash all downloaded inputs and compare the freshly recomputed primary summary with the separately preserved 2025-10-25 result.
def hash_file(path,algorithm):
 h=hashlib.new(algorithm)
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return h.hexdigest()
def sha256_file(path):return hash_file(path,'sha256')
files={
 'salmi_mr_archive':('mr_samples_and_contours.tar.gz',40605003,'ca8e70eeca81feb71321f1a88a24f2f9'),
 'miller_original_weighted':('NICER+XMM_J0740_full.txt',168073694,'c28a3995e60f364b34a66c29a37bf79d'),
 'legred_psr_gw_nicer':('LCEHL_EOS_posterior_samples_PSR+GW+NICER.h5',192213112,'64bdad9b43726162a25546d07305747d')}
source_manifest={}
for label,(filename,expected_bytes,expected_md5) in files.items():
 path=base/filename
 if path.stat().st_size!=expected_bytes:raise ValueError('SOURCE_SIZE_MISMATCH:'+filename)
 md5=hash_file(path,'md5')
 if md5!=expected_md5:raise ValueError('SOURCE_MD5_MISMATCH:'+filename+':'+md5)
 source_manifest[label]={'filename':filename,'bytes':expected_bytes,'md5':md5,'sha256':sha256_file(path)}
primary='KDE_new_bw=0.16|KDE_old_bw=0.16|offset=0.0'
historical=json.loads((base.parent/'J0740_final_weighted_old_source_update.json').read_text())
expected=historical['metrics'][primary]
actual=out['metrics'][primary]
checks={}
for field,tol in [('ESS',0.01),('R14_km',1e-4),('Lambda14',1e-3),('R_at_2.073_km',1e-4),('Mmax_Msun',1e-5)]:
 av=actual[field][1] if isinstance(actual[field],list) else actual[field]
 ev=expected[field][1] if isinstance(expected[field],list) else expected[field]
 checks[field]={'reproduced':av,'historical_2025_10_25':ev,'absolute_delta':abs(av-ev),'tolerance':tol,'pass':abs(av-ev)<=tol}
if not all(x['pass'] for x in checks.values()):raise AssertionError('HISTORICAL_REPRODUCTION_MISMATCH:'+json.dumps(checks))
out['status']='PASS_HISTORICAL_KDE_KDE_REPRODUCTION; NOT_NEW_LEGRED_POSTERIOR; NOT_NATIVE_PHOTON_XPSI'
out['calculation_date']='2026-11-18'
out['method']='Re-execution of the 2025-10-25 KDE/KDE source-posterior-ratio update, using the original weighted Miller rows and original Legred PSR+GW+NICER 10000-EOS ensemble. Salmi and Miller NICER/XMM results are alternative analyses of the same source photons; only the new/old posterior-density ratio replaces the historical J0740 likelihood factor once in the Legred ensemble.'
out['inputs_verified']=source_manifest
out['checks_against_historical_result']=checks
out['historical_result_source']='../J0740_EOS_FINAL_RESULT.json and ../J0740_final_weighted_old_source_update.json'
out['runner_code_sha256']=sha256_file(Path(__file__))
out['new_native_xpsi_photon_likelihood']='NOT_RUN'
out['final_physical_eos_bayes']='NOT_RUN'
output=base.parent/'J0740_reproduction_20261118.json'
output.write_text(json.dumps(out,indent=2,sort_keys=True)+chr(10))
print(json.dumps({'status':out['status'],'samples':{'salmi':int(len(mn)),'miller':int(len(mo)),'legred_eos':int(n)},'primary':actual,'checks':checks,'source_sha256':{k:v['sha256'] for k,v in source_manifest.items()}},indent=2,sort_keys=True))
