"""F51 — Source-locked *measured* extended fixed-spin RNS mass support.

This is not new RNS C integration. It consumes previously computed, SHA-locked
F46 direct C/GR mass-spin roots, F48 independent rescue, and six F38 source-
corrected NICER/XMM KDE likelihoods. No extrapolated stars, no EOS model Bayes.
"""
from __future__ import annotations
import argparse, hashlib, io, json, math, zipfile
from pathlib import Path

import numpy as np
from scipy.integrate import simpson
from scipy.interpolate import RegularGridInterpolator
from scipy.stats import norm

EOS = ('APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2')
SHA = {
 'F38': '4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307',
 'F44': 'b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98',
 'F48': '8217dddfa431d33105421b183b876be3b52cad16525c592459e7f90e8b19b786',
 'F49': '47cf64987a976b75e181bb4bfc06702c73de9835908d758331566f07fa60f22a',
 'F49_JSON': '4600ffa338606847fd2981583f38c44945c01525dd24e950ca5c90a14ccb04e8',
 'APR4_EPP': 'c7a8f4e64ad5b3de92e0b0d924edea8e1a0f10f2d390905324369945dc534c66',
 'ENG': '7b1aea08c5f3cd466fe9b245ededfb5c7c9c87f590111107d09f4e7a028de2ae',
 'MPA1': '0cff4621ddef0da0c02d2bae9a2e45f85d364f05244fd193d3528d336406d70c',
 'MS1': '2fc7266e295a954ef5ca4c7b7a75fc4728c2591ed891bbd1362b46c1d1d23ec8',
 'MS1B': '3975c9561b2a0bdc81ff03b666fcaed8f7666233fd39f9ccf9342575253e867e',
 'WFF1': 'bc4795ab244cc169f5ee5011c3ba1ac4646926a14c982b94d07808d647a955f3',
 'WFF2': '23a59ccc8a606943d54841569a847c3dcf99ff0a251b2d53c248d6d5d809bfcb'
}
MU, SIG, SPIN = 2.082, .0703, 346.536369
OLD_LO, LO, HI = 1.95, 1.89, 2.10
TOP = {'APR4_EPP': 2.15, 'ENG': 2.175, 'MPA1': 2.175,
       'MS1': 2.175, 'MS1B': 2.175, 'WFF1': 2.10, 'WFF2': 2.175}
TOL_M = 1e-4
TOL_HZ = .01


def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):
   h.update(block)
 return h.hexdigest()


def source_zip(path,key):
 if sha(path)!=SHA[key]:raise ValueError('F51_BAD_SHA256_'+key)
 with zipfile.ZipFile(path) as z:
  bad=z.testzip()
  if bad:raise ValueError('F51_BAD_ZIP_MEMBER_'+str(bad))
  return {n:z.read(n) for n in z.namelist()}


def prior_pdf(m):
 a=np.asarray(m,float)
 den=norm.cdf(5)-norm.cdf(-5)
 return np.where((a>=MU-5*SIG)&(a<=MU+5*SIG),norm.pdf((a-MU)/SIG)/(SIG*den),0.)


def prior_probability(lo,hi):
 den=norm.cdf(5)-norm.cdf(-5)
 return float((norm.cdf((hi-MU)/SIG)-norm.cdf((lo-MU)/SIG))/den)


def validate_star(star,target):
 fields=['mass_msun','spin_hz','radius_eq_km','central_energy_density_g_cm3','axis_ratio']
 if not all(k in star and math.isfinite(float(star[k])) for k in fields):
  raise ValueError('F51_BAD_STAR_FIELDS')
 if (abs(float(star['mass_msun'])-target)>TOL_M or abs(float(star['spin_hz'])-SPIN)>TOL_HZ
     or not 6<float(star['radius_eq_km'])<30 or not .85<float(star['axis_ratio'])<=1
     or not .25e15<float(star['central_energy_density_g_cm3'])<4.5e15):
  raise ValueError('F51_BAD_DIRECT_RNS_ROOT_'+str(target))


def load_verified_curves(archives, f44, f48):
 anchors=json.loads(source_zip(f44,'F44')['F44_direct_RNS_seven_candidates.json'])['eos']
 if set(anchors)!=set(EOS):raise ValueError('F51_INCOMPLETE_F44_ANCHORS')
 resc=source_zip(f48,'F48')
 resc_report=json.loads(resc['F48_WFF1_real_direct_rescue.json'])
 if resc_report['status']!='DIRECT_C_GR_WFF1_MISSING_MASS_ROOT_RECOVERED_NOT_PHYSICAL_STABILITY':
  raise ValueError('F51_F48_RECOVERY_NOT_ACCEPTED')
 recovered=json.loads(resc['WFF1_fixed_spin_direct_curve_F48_recovered.json'])
 roots={};extras={};anchors_sha={}
 for name in EOS:
  z=source_zip(archives[name],name)
  source=json.loads(z[f'{name}_fixed_spin_direct_curve.json'])
  if (source['eos']!=name or source['rns_table_sha256']!=anchors[name]['model_table_sha256']
      or source['source_f44_sha256']!=SHA['F44']):
   raise ValueError('F51_MODEL_ANCESTRY_MISMATCH_'+name)
  if not source['rising_density_order_pass']:
   raise ValueError('F51_ORIGINAL_F46_DENSITY_ORDER_FAILED_'+name)
  if name=='WFF1':
   if source['successful_common_targets']!=21:raise ValueError('F51_WFF1_ORIGINAL_FAILURE_NOT_PRESERVED')
   if (recovered['rns_table_sha256']!=source['rns_table_sha256']
       or recovered['source_f44_sha256']!=SHA['F44']):
    raise ValueError('F51_WFF1_RECOVERY_MODEL_MISMATCH')
   use=recovered
  else:
   if source['successful_common_targets']!=22:raise ValueError('F51_F46_COMMON_WINDOW_MISSING_'+name)
   use=source
  d={float(k):v for k,v in use['roots'].items()}
  d[2.073]=use['anchor']
  common=np.array(sorted(set([LO,1.92]+list(map(float,source['common_mass_grid'])))))
  if len(common)!=24 or abs(common[0]-LO)>1e-10 or abs(common[-1]-HI)>1e-10:
   raise ValueError('F51_COMMON_EXTENDED_GRID_INVALID')
  if any(m not in d for m in common):raise ValueError('F51_COMMON_REAL_C_ROOT_MISSING_'+name)
  for m,star in d.items():validate_star(star,m)
  dens=np.array([d[m]['central_energy_density_g_cm3'] for m in common])
  if not np.all(np.diff(dens)>0):raise ValueError('F51_NONMONOTONE_COMMON_BRANCH_'+name)
  upper=max(d)
  if abs(upper-TOP[name])>1e-8:raise ValueError('F51_NEW_RANGE_NOT_DIRECTLY_SUPPORTED_'+name)
  upperm=np.array(sorted(m for m in d if LO-1e-8<=m<=upper+1e-8))
  if not np.all(np.diff([d[m]['central_energy_density_g_cm3'] for m in upperm])>0):
   raise ValueError('F51_NONMONOTONE_EXPLORATORY_BRANCH_'+name)
  roots[name]={'common_m':common,'common_r':np.array([d[m]['radius_eq_km'] for m in common]),
               'max_m':upper,'all_m':upperm,'all_r':np.array([d[m]['radius_eq_km'] for m in upperm]),
               'table_sha256':source['rns_table_sha256'],'f46_zip_sha256':SHA[name],
               'matched_direct_roots_in_extended_common_window':len(common),
               'direct_root_masses_exploratory_above_2p10':list(map(float,[m for m in upperm if m>HI+1e-9]))}
 return roots


def surface(z,n):
 with np.load(io.BytesIO(z[n]),allow_pickle=False) as d:
  m=np.asarray(d['mass_centres'],float);r=np.asarray(d['radius_centres_km'],float)
  L=np.asarray(d['relative_likelihood_L_over_Z'],float)
  mask=np.asarray(d['hard_source_support'],bool)
 if m.shape!=(401,) or r.shape!=(581,) or L.shape!=(401,581) or mask.shape!=L.shape:
  raise ValueError('F51_F38_SHAPE_FAIL')
 if np.any(~np.isfinite(L)) or np.any(L<0) or np.any(L[~mask]!=0):
  raise ValueError('F51_F38_LIKELIHOOD_INVALID')
 return m,r,L,mask


def sample(mgrid,rgrid,L,mask,m,r):
 m=np.asarray(m,float);r=np.asarray(r,float)
 i=np.searchsorted(mgrid,m,side='right')-1
 j=np.searchsorted(rgrid,r,side='right')-1
 if np.any(i<0) or np.any(j<0) or np.any(i>=len(mgrid)-1) or np.any(j>=len(rgrid)-1):
  raise ValueError('F51_OFF_F38_GRID')
 if not np.all(mask[i,j]&mask[i+1,j]&mask[i,j+1]&mask[i+1,j+1]):
  raise ValueError('F51_OFF_F38_HARD_SOURCE_SUPPORT')
 v=RegularGridInterpolator((mgrid,rgrid),L,bounds_error=True)(np.column_stack((m,r)))
 if not np.all(np.isfinite(v)) or np.any(v<0):raise ValueError('F51_LIKELIHOOD_INTERP_INVALID')
 return v


def integral(m,v):
 if len(m)<15 or np.any(np.diff(m)<=0):raise ValueError('F51_INTEGRAL_INVALID_MASSES')
 q=prior_pdf(m)
 value=float(simpson(q*v,x=m))
 trap=float(np.trapezoid(q*v,x=m))
 analytic=prior_probability(m[0],m[-1])
 numeric=float(simpson(q,x=m))
 if abs(numeric-analytic)>5e-4:raise ValueError('F51_PRIOR_NUMERICAL_QUADRATURE_FAIL')
 return {'mass_lo_msun':float(m[0]),'mass_hi_msun':float(m[-1]),
         'mass_prior_coverage':analytic,'likelihood_full_radio_prior_window_contribution':value,
         'conditional_on_verified_mass_window_L_over_Z':value/analytic,
         'simpson_vs_trapezoid_fractional_difference':(value-trap)/max(trap,1e-300),
         'unobserved_mass_tail_prior_fraction':1-analytic}


def run(f38,f44,f48,f49,archive_dict,out):
 rns=load_verified_curves(archive_dict,f44,f48)
 surf=source_zip(f38,'F38')
 if str(f49).endswith('.json'):
  if sha(f49)!=SHA['F49_JSON']:raise ValueError('F51_BAD_SOURCE_F49_GOLDEN_JSON_SHA')
  orig=json.loads(Path(f49).read_text())
 else:
  orig=json.loads(source_zip(f49,'F49')['F49_7EOS_all_22_real_direct_RNS_integrals.json'])
 names=sorted(x for x in surf if x.startswith('posterior_prior_ratio_') and x.endswith('.npz'))
 if len(names)!=6:raise ValueError('F51_NEED_SIX_SOURCE_F38_SURFACES')
 result={'schema':'F51_pinned_F46_F48_F38_mass_support_expansion_v1',
   'status':'F51_NUMERICAL_MASS_SUPPORT_EXPANDED_NOT_NUCLEAR_EOS_BAYES',
   'model_kind':'seven explicitly new, nonunique F42 causal-lift first-law cold-gas candidate EOS (NOT source nuclear EOS)',
   'direct_C_RNS_models_on_common_support':7*24,
   'common_verified_mass_window_msun':[LO,HI],
   'previous_verified_mass_window_msun':[OLD_LO,HI],
   'common_radio_prior_mass_fraction_before':prior_probability(OLD_LO,HI),
   'common_radio_prior_mass_fraction_now':prior_probability(LO,HI),
   'remaining_prior_mass_fraction_uncomputed_for_all_seven':1-prior_probability(LO,HI),
   'source_hashes':{**SHA},
   'observed_frequency_hz':SPIN,
   'physical_eos_microphysics_and_crust_acceptance':'NOT_ESTABLISHED',
   'global_fixed_J_rotating_stability':'NOT_ESTABLISHED',
   'native_photon_XPSI_joint_refit':'NOT_RUN',
   'seven_source_nuclear_EOS_Bayes':'NOT_RUN',
   'old_F49_42_values_max_absolute_reproduction_error':None,
   'upper_exploratory_is_not_common_model_bayes':True,
   'per_eos_real_mass_support':{n:{k:v for k,v in rec.items() if k in ('max_m','table_sha256','f46_zip_sha256','matched_direct_roots_in_extended_common_window','direct_root_masses_exploratory_above_2p10')} for n,rec in rns.items()},
   'surfaces':{}}
 maxerr=0.
 for surface_name in names:
  mg,rg,lv,mask=surface(surf,surface_name)
  scores={};explore={};old={}
  for name,curve in rns.items():
   cm=curve['common_m'];cr=curve['common_r']
   vals=sample(mg,rg,lv,mask,cm,cr)
   scores[name]=integral(cm,vals)
   k=(cm>=OLD_LO-1e-9)
   original=integral(cm[k],vals[k])
   old[name]=original
   expected=orig['surfaces'][surface_name]['seven_integrals'][name]['conditional_on_common_window_source_Z_ratio']
   maxerr=max(maxerr,abs(original['conditional_on_verified_mass_window_L_over_Z']-expected))
   em=curve['all_m'];er=curve['all_r']
   extrap=sample(mg,rg,lv,mask,em,er)
   explore[name]=integral(em,extrap)
  result['surfaces'][surface_name]={'common_24_direct_root_observational_integrals':scores,
     'previous_F49_22_node_window_diagnostic':old,
     'per_EOS_exploratory_actual_direct_C_GR_support_scores_NOT_DIRECTLY_COMPARABLE':explore,
     'new_common_window_highest_score':max(scores,key=lambda k:scores[k]['conditional_on_verified_mass_window_L_over_Z'])}
 if maxerr>1e-8:raise ValueError('F51_OLD_F49_NUMERIC_BASELINE_NOT_REPRODUCED:'+str(maxerr))
 result['old_F49_42_values_max_absolute_reproduction_error']=maxerr
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
 return result


def main():
 p=argparse.ArgumentParser()
 for n in ('f38','f44','f48','f49','curves_dir','out'):p.add_argument('--'+n.replace('_','-'),type=Path,required=True)
 a=p.parse_args()
 archives={name:a.curves_dir/('F46_'+name+'.zip') for name in EOS}
 result=run(a.f38,a.f44,a.f48,a.f49,archives,a.out)
 print(json.dumps({'status':result['status'],'coverage_before':result['common_radio_prior_mass_fraction_before'],
                   'coverage_now':result['common_radio_prior_mass_fraction_now'],
                   'F49_match_max_error':result['old_F49_42_values_max_absolute_reproduction_error'],
                   'all_six_rankings':{k:v['new_common_window_highest_score'] for k,v in result['surfaces'].items()}},indent=2))

if __name__=='__main__':main()
