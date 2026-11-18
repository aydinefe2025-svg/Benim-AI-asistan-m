"""F47: bounded mass-window conditional F38 M-R likelihood for seven direct RNS curves.

Uses exactly the same truncated radio mass prior for each EOS, with source-prior
correction already inside F38 L/Z; no second radio likelihood or mass prior.
These new EOS are nonunique causal-lift F42 hypotheses, NOT the original nuclear
EOS or a complete astrophysical Bayes EOS posterior / compiled photon likelihood.
"""
from __future__ import annotations
import argparse,hashlib,io,json,math,zipfile
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
from scipy.interpolate import RegularGridInterpolator
from scipy.stats import norm

F38_SHA='4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307'
F42_SHA='c8d8cdc9804a702860ab1af65b60fa25dfac0f74fce9ec6347c4271ea3353115'
F44_SHA='b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98'
EOS=('APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2')
M0,M1=1.95,2.10
MU,SIG=2.082,0.0703
SPIN=346.536369


def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()


def prior_window_probability():
 denominator=norm.cdf(5)-norm.cdf(-5)
 return float((norm.cdf((M1-MU)/SIG)-norm.cdf((M0-MU)/SIG))/denominator)


def full_radio_pdf(m):
 m=np.asarray(m,float)
 z=norm.cdf(5)-norm.cdf(-5)
 return np.where((m>=MU-5*SIG-1e-8)&(m<=MU+5*SIG+1e-8),norm.pdf((m-MU)/SIG)/(SIG*z),0.)


def accepted_one_node_gap(name, missing, count, expected):
 """Explicit single failed C root exception; never synthesize an RNS star.

 The common mass *integration bounds* are still identical. Irregular
 Simpson quadrature uses measured nodes only. This is not the F46 22/22 gate.
 """
 if not missing:return []
 if (name!='WFF1' or len(missing)!=1 or abs(float(missing[0])-2.0175)>1e-8
     or count!=expected-1):
  raise ValueError('F46_COMMON_WINDOW_UNSOLVED_MORE_THAN_ONE_OR_UNEXPECTED:'+name)
 return list(missing)


def validate_all_curves(folder, f44):
 if sha(f44)!=F44_SHA:raise ValueError('F44_ANCHOR_ARCHIVE_SHA_MISMATCH')
 with zipfile.ZipFile(f44) as z:
  if z.testzip() is not None:raise ValueError('F44_SOURCE_ZIP_CRC_FAIL')
  anchors=json.loads(z.read('F44_direct_RNS_seven_candidates.json'))['eos']
 if set(anchors)!=set(EOS):raise ValueError('SEVEN_SOURCE_EOS_INCOMPLETE')
 curves={}
 common=None
 for name in EOS:
  p=folder/(name+'_fixed_spin_direct_curve.json')
  if not p.is_file():raise FileNotFoundError('F46_UNAVAILABLE:'+name)
  r=json.loads(p.read_text())
  if r['source_f42_sha256']!=F42_SHA or r['source_f44_sha256']!=F44_SHA or r['eos']!=name:
   raise ValueError('F46_SOURCE_MISMATCH:'+name)
  if r['rns_table_sha256']!=anchors[name]['model_table_sha256']:
   raise ValueError('F46_RNS_TABLE_HASH_MISMATCH:'+name)
  if not r['rising_density_order_pass']:
   raise ValueError('F46_MASS_ORDER_UNVALIDATED:'+name)
  if r['status'] not in ('COMMON_WINDOW_GRID_COMPLETE_NOT_GLOBAL_STABILITY_PROOF','PARTIAL_UNCERTIFIED_MASS_SUPPORT'):
   raise ValueError('F46_ROOTS_UNTRUSTWORTHY:'+name)
  masses=np.array(r['common_mass_grid'],float)
  if common is None: common=masses
  if masses.shape!=common.shape or np.max(np.abs(masses-common))>1e-10:
   raise ValueError('F46_INCONSISTENT_MASS_GRID:'+name)
  if len(masses)<15 or abs(masses[0]-M0)>1e-8 or abs(masses[-1]-M1)>1e-8 or np.any(np.diff(masses)<=0):
   raise ValueError('F46_MASS_WINDOW_INVALID:'+name)
  rows=[];actual_m=[];missing=[]
  for m in masses:
   v=(r['anchor'] if abs(m-2.073)<1e-8 else r['roots'].get(str(m)))
   if v is None:
    missing.append(float(m))
    continue
   if abs(float(v['mass_msun'])-m)>1e-4 or abs(float(v['spin_hz'])-SPIN)>.01:
    raise ValueError('F46_ROOT_RESIDUAL_FAIL:'+name)
   rows.append(v);actual_m.append(float(m))
  accepted_one_node_gap(name,missing,len(rows),len(masses))
  if abs(actual_m[0]-M0)>1e-8 or abs(actual_m[-1]-M1)>1e-8:
   raise ValueError('F46_MASS_WINDOW_ENDPOINT_MISSING:'+name)
  rho=np.array([v['central_energy_density_g_cm3'] for v in rows])
  if not np.all(np.diff(rho)>0):raise ValueError('F46_RISING_BRANCH_MASS_ORDER_FAIL:'+name)
  curves[name]={'m':np.array(actual_m),'r':np.array([v['radius_eq_km'] for v in rows]),
                'central_density':rho,'source_sha256':sha(p),
                'missing_internal_direct_root_masses_msun':missing,'original_f46_status':r['status']}
 return curves


def load_surface(zip_path,filename):
 with zipfile.ZipFile(zip_path) as z:
  if z.testzip() is not None:raise ValueError('F38_ARCHIVE_CRC_ERROR')
  with np.load(io.BytesIO(z.read(filename)),allow_pickle=False) as a:
   m=np.asarray(a['mass_centres'],float)
   r=np.asarray(a['radius_centres_km'],float)
   v=np.asarray(a['relative_likelihood_L_over_Z'],float)
   support=np.asarray(a['hard_source_support'],bool)
 if m.shape!=(401,) or r.shape!=(581,) or v.shape!=(401,581) or support.shape!=v.shape:
  raise ValueError('F38_SURFACE_SHAPE_MISMATCH')
 if not np.all(np.diff(m)>0) or not np.all(np.diff(r)>0) or np.any(~np.isfinite(v)) or np.any(v<0) or np.any(v[~support]!=0):
  raise ValueError('F38_SURFACE_INTEGRITY_FAIL')
 return m,r,v,support


def sample_masked(mgrid,rgrid,values,support, m,r):
 m=np.asarray(m,float);r=np.asarray(r,float)
 i=np.searchsorted(mgrid,m,side='right')-1
 j=np.searchsorted(rgrid,r,side='right')-1
 if np.any(i<0)|np.any(i>=len(mgrid)-1)|np.any(j<0)|np.any(j>=len(rgrid)-1):
  raise ValueError('F38_INPUT_OUTSIDE_GRID_OR_RADIUS_CEILING')
 if not (support[i,j]&support[i+1,j]&support[i,j+1]&support[i+1,j+1]).all():
  raise ValueError('F38_HARD_SUPPORT_MASK_INTERSECTION')
 z=RegularGridInterpolator((mgrid,rgrid),values,bounds_error=True)(np.c_[m,r])
 if not np.all(np.isfinite(z)) or np.any(z<0):raise ValueError('F38_INVALID_SAMPLED_VALUES')
 return z


def integrate_curve(m,L):
 m=np.asarray(m,float);L=np.asarray(L,float)
 if (m.ndim!=1 or m.size<15 or m.shape!=L.shape or np.any(np.diff(m)<=0)
    or abs(m[0]-M0)>1e-8 or abs(m[-1]-M1)>1e-8 or np.any(~np.isfinite(L)) or np.any(L<0)):
  raise ValueError('INTEGRAND_NOT_FULL_DECLARED_WINDOW')
 q=full_radio_pdf(m)
 window_prob=prior_window_probability()
 value=float(simpson(q*L,x=m))
 simple=float(np.trapezoid(q*L,x=m))
 prior_normalization=float(simpson(q,x=m))
 if abs(prior_normalization-window_prob)>1e-4:
  raise ValueError('NUMERICAL_RADIO_PRIOR_NORMALIZATION_FAIL')
 return {'window_contribution_to_full_prior_source_Z_ratio':value,
         'conditional_on_common_window_source_Z_ratio':value/window_prob,
         'simpson_minus_trap_percent':100*(value/simple-1) if simple>0 else None,
         'radio_prior_window_probability':window_prob,
         'quadrature_window_mass_normalization':prior_normalization,
         'uncomputed_full_prior_outside_window_probability':1-window_prob}


def run(f38,f44,curves_dir,out):
 if sha(f38)!=F38_SHA:raise ValueError('F38_ORIGINAL_KDE_ARCHIVE_SHA_MISMATCH')
 curves=validate_all_curves(curves_dir,f44)
 j={'schema':'j0740_F47_7_new_candidate_common_mass_window_marginalized_L_over_sourceZ_v1',
    'status':'FAIL_CLOSED_SOURCE_REQUIRED','source_F38_sha256':F38_SHA,
    'source_F44_sha256':F44_SHA,'source_F42_sha256':F42_SHA,
    'common_mass_window_msun':[M0,M1],
    'same_original_radio_mass_prior_applied_once':'N(2.082,0.0703²) +/-5sigma normalized on full source support',
    'radio_mass_prior_probability_in_common_window':prior_window_probability(),
    'EOS_physical_microphysics_accepted':'NOT_ESTABLISHED',
    'global_rotating_fixed_J_stability':'NOT_ESTABLISHED',
    'compiled_photon_level_XPSI_refit':'NOT_RUN',
    'full_seven_model_Bayes_posterior':'NOT_RUN',
    'mass_uncovered_prior_likelihood':'UNKNOWN_NOT_ASSUMED_ZERO',
    'note':'Only conditional common-window integrals for seven new artificial cold-gas causal-lift EOS candidates; original nuclear EOS not validated',
    'curve_sha256':{n:v['source_sha256'] for n,v in curves.items()},
    'missing_direct_RNS_targets':{n:v['missing_internal_direct_root_masses_msun'] for n,v in curves.items()},
    'F46_original_CI_status':'ONE_WFF1_ROOT_TOLERANCE_FAILURE__NO_INTERPOLATED_STAR',
    'F46_mixed_grid_acceptance':'6_OF_7_22_OF_22_AND_WFF1_21_OF_22; COMMON_MASS_INTERVAL_ENDPOINTS_COMPLETE',
    'integration_numerics':'Actual uneven-grid Simpson mass quadrature; no stellar root invented at missing WFF1 point',
    'surfaces':{}}
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(j,indent=2,sort_keys=True)+'\n')
 with zipfile.ZipFile(f38) as z:
  names=sorted(x for x in z.namelist() if x.startswith('posterior_prior_ratio_') and x.endswith('.npz'))
 if len(names)!=6:raise ValueError('F38_SIX_SOURCE_SURFACES_REQUIRED')
 for filename in names:
  mg,rg,v,s=load_surface(f38,filename)
  vals={}
  for name,curve in curves.items():
   samples=sample_masked(mg,rg,v,s,curve['m'],curve['r'])
   vals[name]=integrate_curve(curve['m'],samples)
  # Normalization below is purely hypothetical equal-prior *restricted-window*
  # diagnostic: never claim physically justified EOS posterior.
  scores={n:rec['conditional_on_common_window_source_Z_ratio'] for n,rec in vals.items()}
  Z=sum(scores.values())
  normalized={n:(scores[n]/Z if Z>0 else None) for n in EOS}
  j['surfaces'][filename]={'seven_integrals':vals,
    'highest_conditional_common_window_model':max(scores,key=scores.get),
    'conditional_scores_relative_to_best':{n:(scores[n]/max(scores.values()) if max(scores.values())>0 else None) for n in EOS},
    'equal_model_prior_hypothetical_window_normalized_weights_not_EOS_posterior':normalized,
    'interpretation':'F38 approximate source-prior corrected KDE surface, shared radio mass prior; no extrapolation, no global physics acceptance'}
  out.write_text(json.dumps(j,indent=2,sort_keys=True,allow_nan=False)+'\n')
 j['status']='SEVEN_CONDITIONAL_COMMON_WINDOW_INTEGRALS_WITH_ONE_WFF1_INTERNAL_ROOT_GAP_NOT_FULL_BAYES'
 out.write_text(json.dumps(j,indent=2,sort_keys=True,allow_nan=False)+'\n')
 return j


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--f38',type=Path,required=True)
 p.add_argument('--f44',type=Path,required=True)
 p.add_argument('--curves-dir',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();j=run(a.f38,a.f44,a.curves_dir,a.out)
 print(json.dumps({'status':j['status'],'surface_rankings':{k:v['highest_conditional_common_window_model'] for k,v in j['surfaces'].items()}},sort_keys=True))
if __name__=='__main__':main()
