"""F50: published J0740 radius-summary sensitivity diagnostic, NOT an EOS likelihood.

Source-locked RNS geometric predictions at M=2.073 solar masses from F44.
Do not multiply these dependent NICER/XMM posterior summaries, infer Bayes
factors, discard a model using marginal-68% interval, or treat the F42
hypothetical barotropes as the native nuclear EOS.
"""
from __future__ import annotations
import hashlib, json, math, sys, zipfile
from pathlib import Path

F44_SHA = 'b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98'
TARGET_MASS=2.073
TARGET_SPIN=346.536369
# Source URLs are specific published abstracts/papers; all intervals are marginal 68% credible summaries.
# The Salmi and Huang studies share the same 2018-2022 NICER event list and XMM measurements.
PUBLIC_STUDIES=(
 {'key':'Riley2021','median_km':12.39,'minus_km':0.98,'plus_km':1.30,'url':'https://arxiv.org/abs/2105.06980','underlying_data':'NICER_XMM_early'},
 {'key':'Miller2021','median_km':13.70,'minus_km':1.50,'plus_km':2.60,'url':'https://ntrs.nasa.gov/citations/20210026095','underlying_data':'NICER_XMM_early'},
 {'key':'Salmi2024','median_km':12.49,'minus_km':0.88,'plus_km':1.28,'url':'https://doi.org/10.3847/1538-4357/ad5f1f','underlying_data':'NICER_XMM_2018_2022'},
 {'key':'Dittmann2024','median_km':12.92,'minus_km':1.13,'plus_km':2.09,'url':'https://arxiv.org/abs/2406.14467','underlying_data':'NICER_XMM_2018_2022'},
 {'key':'Huang2026_shifted_dipole','median_km':13.28,'minus_km':1.07,'plus_km':1.47,'url':'https://arxiv.org/abs/2609.37928','underlying_data':'NICER_XMM_2018_2022'},
 {'key':'Huang2026_centered_DQ','median_km':17.46,'minus_km':1.48,'plus_km':1.57,'url':'https://arxiv.org/abs/2609.37928','underlying_data':'NICER_XMM_2018_2022'},
)


def sha(path: Path) -> str:
 return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rns(f44: Path):
 if sha(f44)!=F44_SHA: raise ValueError('F44_SOURCE_SHA_MISMATCH')
 with zipfile.ZipFile(f44) as z:
  if z.testzip() is not None:raise ValueError('F44_ZIP_CRC_FAIL')
  j=json.loads(z.read('F44_direct_RNS_seven_candidates.json'))
 if abs(float(j['fixed_mass_msun'])-TARGET_MASS)>1e-8 or abs(float(j['fixed_frequency_hz'])-TARGET_SPIN)>1e-6:
  raise ValueError('RNS_TARGET_MASS_SPIN_MISMATCH')
 if len(j['eos'])!=7 or j.get('physical_7candidate_acceptance')=='PASS':
  raise ValueError('SOURCE_CANDIDATE_IDENTITY_INVALID')
 out={}
 for name,row in j['eos'].items():
  fine=row['fine_mesh']['root'];coarse=row['coarse_mesh']['root']
  if row['fine_mesh']['status']!='DIRECT_RNS_MASS_SPIN_ROOT_PASS':
   raise ValueError('DIRECT_RNS_FINE_ROOT_NOT_PASS:'+name)
  if abs(fine['mass_msun']-TARGET_MASS)>1e-4 or abs(fine['spin_hz']-TARGET_SPIN)>1e-2:
   raise ValueError('RNS_ROOT_RESIDUAL_TOO_LARGE:'+name)
  r=float(fine['radius_eq_km'])
  if not (8<r<20):raise ValueError('NONPHYSICAL_RNS_RADIUS:'+name)
  delta=abs(r-float(coarse['radius_eq_km']))*1000
  if delta>30.0:raise ValueError('MESH_RADIUS_GATE_FAIL:'+name)
  out[name]={'R_equatorial_km':r,'grid_delta_m':delta,'mass_msun':float(fine['mass_msun']),
             'spin_hz':float(fine['spin_hz']),'hypothetical_F42_EOS_not_original_nuclear_model':True}
 return out


def diagnostic_flag(radius, study):
 l=study['median_km']-study['minus_km'];h=study['median_km']+study['plus_km']
 if radius<l: status='below_marginal_68_interval_not_exclusion'
 elif radius>h: status='above_marginal_68_interval_not_exclusion'
 else:status='within_marginal_68_interval_not_evidence'
 return {'label':status,'distance_from_median_km':radius-study['median_km'],
         'marginal_interval_km':[l,h]}


def audit(f44: Path):
 stars=read_rns(f44)
 studies=[dict(x, lower_68km=x['median_km']-x['minus_km'],upper_68km=x['median_km']+x['plus_km']) for x in PUBLIC_STUDIES]
 return {'schema':'J0740_F50_crossmodel_radius_consistency_diagnostic_v1',
   'status':'PUBLISHED_RADIUS_MODEL_SYSTEMATICS_COMPARED_NOT_INDEPENDENT_EVIDENCE',
   'fixed_mass_Msun':TARGET_MASS,'spin_Hz':TARGET_SPIN,'source_F44_sha256':F44_SHA,
   'same_photons_salmi2024_dittmann2024_huang2026':True,
   'do_not_multiply_posteriors_or_Bayes_factors':True,
   'huang2026_delta_lnZ_5p65_is_hotspot_geometry_NOT_nuclear_EOS_Bayes':True,
   'huang2026_centered_model_fraction_R_gt_16km':0.838,
   'observed_marginal_radius_summaries':studies,
   'seven_new_hypothetical_EOS_fixed_mass_RNS':{
     name:dict(model,comparison={s['key']:diagnostic_flag(model['R_equatorial_km'],s) for s in PUBLIC_STUDIES})
     for name,model in stars.items()},
   'mass_radius_posterior_correlation_not_accounted_for':True,
   'independent_photon_likelihood_recomputed':'NOT_RUN',
   'full_support_EOS_model_evidence':'NOT_RUN',
   'physical_EOS_microphysics_acceptance':'NOT_ESTABLISHED',
   'interpretation':'Descriptive posterior-interval and RNS fixed-mass overlay ONLY. No model likelihood or Bayes factors.'}


def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--f44',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
 j=audit(a.f44);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(j,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':j['status'],'eos_count':len(j['seven_new_hypothetical_EOS_fixed_mass_RNS']),
                   'shared_photon_data':j['same_photons_salmi2024_dittmann2024_huang2026']},sort_keys=True))
if __name__=='__main__':main()
