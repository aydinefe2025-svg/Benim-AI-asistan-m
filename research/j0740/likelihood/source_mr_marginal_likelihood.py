#!/usr/bin/env python3
"""Source-derived, nuisance-marginalized PSR J0740 M-R relative likelihood.

Identity: p(M,R|D) / pi_eff(M,R) = L_eff(D|M,R)/Z,
where nuisance parameters are integrated with exactly the source conditional
prior. This uses *published marginalized posterior*, NOT a new photon fit.

The density reconstruction is a Gaussian-smoothed histogram with a hard
source-support mask and boundary normalization, not an exact likelihood.
Outputs are exploratory approximate likelihood surfaces until KDE
bandwidth/Monte Carlo uncertainty and EOS source physics are validated.
"""
from __future__ import annotations
import argparse, hashlib, io, json, math, tarfile
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.stats import truncnorm
from f33_prior_source import (source_mr_support, R_MIN_KM, R_MAX_KM,
    M_MU, M_SIG, POSTERIOR_TAR_SHA256)

S_MR=0.5780634948872538
MR_MMIN=M_MU-5*M_SIG
MR_MMAX=M_MU+5*M_SIG
SOURCE_MD5='ca8e70eeca81feb71321f1a88a24f2f9'
RUNS={'weighted':('J0740_gamma_NxX_lp40k_se001_wmrsamples.dat',1137394,3),
      'resampled':('J0740_gamma_NxX_lp40k_se001_mrsamples_post_equal_weights.dat',379669,2)}

def sha_file(path,method='sha256'):
 h=hashlib.new(method)
 with open(path,'rb') as f:
  for part in iter(lambda:f.read(1<<20),b''):h.update(part)
 return h.hexdigest()

def samples(tar,which):
 suffix,N,COLS=RUNS[which]
 candidates=[x for x in tar.getmembers() if x.name.endswith(suffix)]
 if len(candidates)!=1:raise ValueError('SOURCE_MEMBER_MISSING_OR_AMBIGUOUS:'+suffix)
 data=np.loadtxt(tar.extractfile(candidates[0]),dtype=np.float64,ndmin=2)
 if data.shape!=(N,COLS):raise ValueError(f'WRONG_SOURCE_MATRIX_SHAPE:{data.shape} expected {(N,COLS)}')
 if which=='weighted':w,m,r=data[:,0],data[:,1],data[:,2]
 else:m,r=data[:,0],data[:,1];w=np.ones(N,dtype=float)
 if not (np.isfinite(w).all() and np.isfinite(m).all() and np.isfinite(r).all()):
  raise ValueError('SOURCE_NONFINITE')
 if np.any(w<=0):raise ValueError('SOURCE_WEIGHT_NONPOSITIVE')
 if not all(np.any(m<=x) and np.any(m>=x) for x in (M_MU,)):
  raise ValueError('SOURCE_MASS_COVERAGE_MISSING')
 if not np.all(source_mr_support(m,r)):
  raise ValueError('SOURCE_HARD_PRIOR_SUPPORT_VIOLATION')
 return (w/w.sum()).copy(),m.copy(),r.copy(),candidates[0].name

def grid_geometry(nm=401,nr=581):
 M_edges=np.linspace(MR_MMIN,MR_MMAX,nm+1)
 R_edges=np.linspace(R_MIN_KM,R_MAX_KM,nr+1)
 M=(M_edges[1:]+M_edges[:-1])/2;R=(R_edges[1:]+R_edges[:-1])/2
 dm=float(M_edges[1]-M_edges[0]);dr=float(R_edges[1]-R_edges[0])
 mask=source_mr_support(M[:,None],R[None,:])
 prior_m=truncnorm.pdf(M,-5,5,loc=M_MU,scale=M_SIG)
 prior=np.broadcast_to(prior_m[:,None]/((R_MAX_KM-R_MIN_KM)*S_MR),mask.shape).copy()*mask
 raw_prior_integral=float(prior.sum()*dm*dr)
 if abs(raw_prior_integral-1)>0.003:raise ValueError(f'PRIOR_GRID_NORMALIZATION_DRIFT:{raw_prior_integral}')
 prior/=raw_prior_integral
 return M_edges,R_edges,M,R,dm,dr,mask,prior,raw_prior_integral

def fit(m,r,w,geometry,sm=.025,sr=.35):
 M_edges,R_edges,M,R,dm,dr,mask,prior,prior_unnormalized=geometry
 if sm<dm*1.5 or sr<dr*1.5:raise ValueError('KERNEL_UNDERSAMPLED')
 H=np.histogram2d(m,r,bins=(M_edges,R_edges),weights=w)[0]
 if abs(H.sum()-1)>5e-6:raise ValueError('POSTERIOR_OUTSIDE_GRID')
 s=(sm/dm,sr/dr)
 num=gaussian_filter(H,sigma=s,mode='constant',truncate=4.5)
 frac=gaussian_filter(mask.astype(float),sigma=s,mode='constant',truncate=4.5)
 # Boundaries: p_obs ~ convolution(density*support)/convolution(support),
 # with local-constant correction on the hard prior support.
 corrected=np.divide(num,frac,out=np.zeros_like(num),where=(frac>1e-8))*mask
 norm=float(corrected.sum())
 if norm<=0:raise ValueError('POSTERIOR_NORMALIZATION_ZERO')
 post=corrected/norm/(dm*dr)
 like=np.divide(post,prior,out=np.zeros_like(post),where=mask&(prior>0))
 Z=float((like*prior).sum()*dm*dr)
 if abs(Z-1)>1e-10:raise AssertionError('LIKELIHOOD_MEASURE_NONNORMALIZED')
 if np.any(~np.isfinite(like)) or np.any(like<0):raise AssertionError('LIKELIHOOD_NONFINITE')
 means={'mass':float(np.sum(post*M[:,None])*dm*dr),
        'radius':float(np.sum(post*R[None,:])*dm*dr)}
 return {'posterior':post,'likelihood_ratio':like,
         'mass_mean_post':means['mass'],'radius_mean_post':means['radius'],
         'zero_support_leakage':bool(np.all(post[~mask]==0)),
         'unnormalized_source_prior_grid_integral':prior_unnormalized,
         'posterior_before_boundary_normalization':norm,
         'normalization_check':Z,'kernel_sigmas_m_r':[sm,sr]}

def point(M,R,fit_result,geom):
 M_edges,R_edges,mm,rr,dm,dr,mask,prior,_=geom
 if not bool(source_mr_support(M,R)):return {'status':'OUTSIDE_SOURCE_SUPPORT'}
 fi=(M-M_edges[0])/dm-.5;fj=(R-R_edges[0])/dr-.5
 if not (0<=fi<len(mm)-1 and 0<=fj<len(rr)-1):return {'status':'OUTSIDE_INTERIOR_GRID'}
 val=float(map_coordinates(fit_result['likelihood_ratio'],np.array([[fi],[fj]]),order=1,mode='nearest')[0])
 return {'status':'WITHIN_SOURCE_SUPPORT','likelihood_ratio':val}

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path)
 p.add_argument('--outdir',required=True,type=Path);p.add_argument('--nm',type=int,default=401)
 p.add_argument('--nr',type=int,default=581);a=p.parse_args()
 a.outdir.mkdir(parents=True,exist_ok=True)
 if sha_file(a.source)!=POSTERIOR_TAR_SHA256 or sha_file(a.source,'md5')!=SOURCE_MD5:
  raise ValueError('ORIGINAL_SALMI_SOURCE_SHA256_MD5_FAIL_CLOSED')
 geom=grid_geometry(a.nm,a.nr)
 M_edges,R_edges,M,R,dm,dr,mask,prior,prior_int=geom
 chosen=[(.015,.20),(.025,.35),(.04,.5)]
 results={}
 srcmeta={}
 with tarfile.open(a.source,'r:gz') as tar:
  for kind in RUNS:
   w,m,r,member=samples(tar,kind)
   srcmeta[kind]={'rows':len(m),'member':member,'mass_mean':float(np.dot(w,m)),
                  'radius_mean':float(np.dot(w,r)),
                  'kish_weight_ess_not_independent_samples':float(1/np.dot(w,w))}
   for sm,sr in chosen:
    key=f'{sm:.3f}_{sr:.2f}'
    v=fit(m,r,w,geom,sm,sr)
    points={name:point(2.073,ra,v,geom) for name,ra in {
      'causal_APR4_F36_RNS':10.782043513931155,
      'causal_APR4_F36_crosscheck':10.782286602464971,
      'ENG_legacy_unaccepted':11.59,'MPA1_legacy_unaccepted':12.53,
      'MS1_legacy_unaccepted':15.26,'MS1B_legacy_unaccepted':14.99}.items()}
    if not all(x['status']=='WITHIN_SOURCE_SUPPORT' for x in points.values()):
     raise ValueError('POINT_EVALUATION_SUPPORT_ERROR')
    ref=points['MPA1_legacy_unaccepted']['likelihood_ratio']
    summary={'source_kind':kind,'bandwidth':[sm,sr],
       'posterior_mean_mass_Msun':v['mass_mean_post'],
       'posterior_mean_R_km':v['radius_mean_post'],
       'prior_grid_unrenormalized_mass':v['unnormalized_source_prior_grid_integral'],
       'likelihood_normalization':v['normalization_check'],
       'source_prior_support_zero_leakage':v['zero_support_leakage'],
       'point_relative_likelihood_to_MPA1_diagnostic':{name:float(x['likelihood_ratio']/ref) for name,x in points.items()},
       'point_L_over_Z':points}
    results[f'{kind}_{key}']=summary
    np.savez_compressed(a.outdir/f'posterior_prior_ratio_{kind}_{key}.npz',
         mass_centres=M,radius_centres_km=R,hard_source_support=mask,
         source_effective_prior=prior.astype(np.float32),
         source_marginalized_posterior=v['posterior'].astype(np.float32),
         relative_likelihood_L_over_Z=v['likelihood_ratio'].astype(np.float32),
         sigma_M_Msun=sm,sigma_R_km=sr,
         units='mass=M_sun;radius=km;relative likelihood dimensionless')
    print('RESULT',kind,key,summary['point_relative_likelihood_to_MPA1_diagnostic'],flush=True)
   del w,m,r
 vals=[]
 for bw in chosen:
  key=f'{bw[0]:.3f}_{bw[1]:.2f}'
  left=results[f'weighted_{key}']['point_relative_likelihood_to_MPA1_diagnostic']
  right=results[f'resampled_{key}']['point_relative_likelihood_to_MPA1_diagnostic']
  for name in left:vals.append(100*abs(right[name]/left[name]-1))
 report={'schema':'j0740-source-posterior-to-nuisance-marginalized-likelihood-v1',
   'status':'PASS_APPROXIMATE_POSTERIOR_DIVIDED_BY_SOURCE_MR_PRIOR; NOT_NATIVE_PHOTON_REEVALUATION',
   'mathematical_identity':'p(M,R|D)/pi_eff(M,R) = L_nuisance_marginalized(D|M,R)/Z, subject to exact source prior & posterior',
   'relative_only':True,'original_posterior_sha256':POSTERIOR_TAR_SHA256,
   'source_prior_SMR':S_MR,'source_prior_sourced_code_sha256':'ecabb879c38d4e4e343e5e304e1be39d87a7b0a35d7077454e4677ea1458aa93',
   'source_prior_includes_radio_mass_gaussian':True,
   'single_mass_reference_msun':2.073,
   'source_posterior_records':srcmeta,'results':results,
   'grid':{'nm':a.nm,'nr':a.nr,'M_min':MR_MMIN,'M_max':MR_MMAX,
           'R_min_km':R_MIN_KM,'R_max_km':R_MAX_KM,'dm':dm,'dr':dr},
   'max_relative_weighted_vs_resampled_percent':float(max(vals)),
   'not_eos_bayes':'EOS mass prior and physical EOS eligibility not fixed; these points are not model evidences',
   'not_native_xpsi':'No photon/event-level X-PSI recompilation: uses published M-R marginal posterior; KDE boundary and bandwidth systematic remain.'}
 (a.outdir/'source_likelihood_report.json').write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf8')
 print('FINAL',json.dumps({'status':report['status'],'max_weighted_equal_percent':max(vals),
      'main':results['weighted_0.025_0.35']['point_relative_likelihood_to_MPA1_diagnostic']},sort_keys=True),flush=True)
 return report

if __name__=='__main__':main()