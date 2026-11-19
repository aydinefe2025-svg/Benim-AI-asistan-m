#!/usr/bin/env python3
"""Recover authentic 7 original JESTER/LALSuite RNS-C GR mass sequences from prior CI.

WFF1/2 reached their observed-mass branches and sampled their post-peak falloff
before a far-high-density 180s RNS timeout. This reuses the archived C stars;
no fabricated solver outputs, reruns, EOS alterations, or 12.9GB TAR reads.
Finite mass-increasing branch only. NOT a constant-J stability certificate.
Optional F38 source-likelihood integration is a conditional rotating EOS KDE
model diagnostic, NOT a native event-level X-PSI Bayes factor.
"""
from __future__ import annotations
import argparse, base64, hashlib, io, json, math, sys, zipfile
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.integrate import simpson
from scipy.stats import truncnorm

HERE=Path(__file__).resolve().parent
SEVEN={
 'APR4_EPP':'639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88',
 'ENG':'702da3ddf7c10b0091af5d8c0d576a9e9a85a85726849a2860bdd8ef3643f953',
 'MPA1':'0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22',
 'MS1':'531530be6253984622f667f454f825ccd13fa4e8960a1411aefe5dd7ea5ff3ad',
 'MS1B':'7a3302e8f2541469fc9ba26dbe52f97b1c8696b71864a208ca43ca7f5cde984c',
 'WFF1':'119b8a25435faeddf00f5d3638f3ff2ff00283ce60caacc24cc37c6e2e030ed3',
 'WFF2':'eb08edc3723fc32d428b3dc3b21aa612dad8a3bdb5da6246faedbb7ed65683ae'
}
M_REF={'APR4_EPP':10.754850283,'ENG':11.587725250,'MPA1':12.533295930,
       'MS1':15.258445346,'MS1B':14.985468809,'WFF1':9.975731674,'WFF2':10.623929893}
SPIN_HZ=346.536369
F61_SHA='7b2cbcf6df2dc55d33046d9af587dba179dcb2ec77bad0395e628742479cce0a'
JESTER_COMMIT='e6768650ce992abfd1153a6833857572fe5cd230'
RNS_COMMIT='97e85d325a33e37f702306414533f6cd77812477'
MASS_MU=2.082;MASS_SIGMA=.0703;MASS_LO=MASS_MU-5*MASS_SIGMA;MASS_HI=MASS_MU+5*MASS_SIGMA
F38_EXPECTED_SHA='4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307'
SIX_KEYS=('weighted_0.015_0.20','weighted_0.025_0.35','weighted_0.040_0.50',
          'resampled_0.015_0.20','resampled_0.025_0.35','resampled_0.040_0.50')

class EvidenceFailure(ValueError): pass

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def load_archived_original(root:Path, model:str, manifest:dict):
 if model not in SEVEN:raise EvidenceFailure('unknown source EOS')
 a=manifest['artifacts'][model]
 path=root/a['file']
 if not path.is_file():raise EvidenceFailure('missing pinned original GitHub artifact '+model)
 try:
  data=base64.b64decode(path.read_text().strip(),validate=True)
 except Exception as e:raise EvidenceFailure('original artifact base64 corrupt') from e
 if sha(data)!=a['zip_sha256']:raise EvidenceFailure('GitHub original artifact ZIP SHA256 wrong '+model)
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  if z.testzip() is not None:raise EvidenceFailure('original ZIP failed CRC '+model)
  sourcejson=z.read(a['json_name'])
  if sha(sourcejson)!=a['json_sha256']:raise EvidenceFailure('original RNS star JSON SHA256 wrong '+model)
  x=json.loads(sourcejson)
  rns_table=next((n for n in z.namelist() if n.endswith('.rns')),None)
  if rns_table is None or sha(z.read(rns_table))!=x['RNS_source_input_table_sha256']:
   raise EvidenceFailure('original C RNS table SHA mismatch '+model)
 if x['EOS']!=model or x['source_original_npz_sha256']!=SEVEN[model] or x['F61_source_sha256']!=F61_SHA:
  raise EvidenceFailure('model source-original NPZ or F61 link mismatch '+model)
 if x['RNS_source_commit']!=RNS_COMMIT or x['JESTER_source_commit']!=JESTER_COMMIT:
  raise EvidenceFailure('RNS/JESTER source commit mismatch '+model)
 if x.get('original_EOS_modified') is not False or x.get('model_physical_EOS_admissibility')!='NOT_ESTABLISHED':
  raise EvidenceFailure('source EOS must remain original and not physically certified')
 if abs(x['requested_spin_hz']-SPIN_HZ)>1e-10:raise EvidenceFailure('source spin mismatch')
 if x['source_original_npz_sha256']!=SEVEN[model]:raise EvidenceFailure('wrong source hash')
 return x

def valid_direct_C_branch(model:str,x:dict):
 """Reject raw-star fabrication, test post-peak timeout explicitly, replay selection."""
 raw=x['raw_C_rotating_stars']
 expected=41 if model=='WFF1' else 42 if model=='WFF2' else 48
 if len(raw)!=expected or len(x['failed_source_C_evaluations'])!=0:
  raise EvidenceFailure(f'{model}: archived source original solver star count changed')
 if model.startswith('WFF'):
  gate=x.get('failing_gate',{})
  if x['status']!='NUMERICAL_RECONSTRUCTION_NOT_ACCEPTED' or gate.get('type')!='TimeoutExpired' or '180 seconds' not in gate.get('message',''):
   raise EvidenceFailure(f'{model}: not the original high-density C 180s timeout')
 else:
  if x['status']!='ORIGINAL_EOS_ROTATING_FULL_C_SEQUENCE_SAMPLED_AND_CROSSCHECKED_NOT_PHYSICALLY_CERTIFIED':
   raise EvidenceFailure(model+': archived source success claim changed')
 a=sorted(raw,key=lambda z:z['central_energy_density_g_cm3'])
 m=np.array([star['mass_msun'] for star in a],dtype=float)
 d=np.array([star['central_energy_density_g_cm3'] for star in a],dtype=float)
 r=np.array([star['radius_eq_km'] for star in a],dtype=float)
 f=np.array([star['spin_hz_reported'] for star in a],dtype=float)
 if not(np.all(np.isfinite(m)) and np.all(np.isfinite(d)) and np.all(np.isfinite(r)) and np.all(np.isfinite(f))
        and np.all(np.diff(d)>0) and np.all((m>0.5)&(m<3.5)) and np.all((r>7)&(r<20)) and np.max(abs(f-SPIN_HZ))<.25000001):
  raise EvidenceFailure(model+': raw actual C star numerical physics mismatched')
 peak=int(np.argmax(m)); endmass=float(m[peak]); post=len(a)-peak-1
 if model.startswith('WFF') and (post<2 or float(m[peak]-m[-1])<.003):
  raise EvidenceFailure(model+': timeout before a witnessed post-peak mass drop; cannot recover')
 selected=[];deleted=[]
 for star in a[:peak+1]:
  if not selected or star['mass_msun']>selected[-1]['mass_msun']+.00001:
   selected.append(star)
  else:
   deleted.append({'central_density':star['central_energy_density_g_cm3'],'mass':star['mass_msun']})
 if len(selected)<30 or not(selected[0]['mass_msun']<2.073<selected[-1]['mass_msun']):
  raise EvidenceFailure(model+': raw star branch does not contain exact target')
 mm=np.array([z['mass_msun'] for z in selected]);rr=np.array([z['radius_eq_km'] for z in selected])
 rr_func=PchipInterpolator(mm,rr,extrapolate=False)
 r073=float(rr_func(2.073));delta=r073-M_REF[model]
 if abs(delta)>.05:raise EvidenceFailure(model+': RNS sweep does not reproduce independent direct C M=2.073 radius')
 coverage=float(truncnorm.cdf(min(MASS_HI,mm[-1]),-5,5,loc=MASS_MU,scale=MASS_SIGMA)-truncnorm.cdf(max(MASS_LO,mm[0]),-5,5,loc=MASS_MU,scale=MASS_SIGMA))
 if not 0<=coverage<=1.00001:raise EvidenceFailure('mass coverage wrong')
 return dict(original_model=model,raw_original_solver_count=len(raw),valid_increasing_branch_stars=len(selected),
      accepted_numeric_source_mass_range_msun=[float(mm[0]),float(mm[-1])],
      sampled_most_massive_source_star_msun=endmass,observed_after_peak_count=post,
      highest_density_mass_drop_below_peak_msun=float(m[peak]-m[-1]),
      radius_at_original_direct_C_2p073_msun_km=r073,
      independent_direct_C_target_radius_km=M_REF[model],
      massline_vs_exact_C_target_R_delta_m=float(1000*delta),
      source_radio_mass_prior_covered_fraction=coverage,
      high_density_solver_timeout_recovered=model.startswith('WFF'),
      original_timeout_not_misreported_as_success=model.startswith('WFF'),
      original_attempted_points_48=True,
      not_attempted_or_not_completed_high_density_asymptotic_points=48-len(raw),
      source_selected_model_arrays={'mass_msun':mm.tolist(),'radius_eq_km':rr.tolist()},
      rejected_nonincreasing_sampled_mass_stars=deleted,
      physical_EOS_global_admissibility='NOT_ESTABLISHED',
      continuous_constant_J_stability='NOT_ESTABLISHED')

def load_all(root:Path):
 raw_manifest=(root/'archived_artifact_manifest.json').read_bytes()
 manifest=json.loads(raw_manifest)
 if manifest['source_C_job_run_id']!=44565658458 or set(manifest['artifacts'])!=set(SEVEN):
  raise EvidenceFailure('not the true 7 source RNS CI original provenance')
 result={};origin={}
 for label in SEVEN:
  x=load_archived_original(root/'artifacts',label,manifest)
  result[label]=valid_direct_C_branch(label,x);origin[label]=x
 return result,origin,manifest

def observed_rotating_KDE_inference(result:dict,f38zip:Path,n:int=4001):
 # Reuse the exact same source-prior support and q/pi_eff from F38 as the previous
 # original 7-EOS STATIC result, switching only to authentic rotating GR curves.
 repo=Path(__file__).resolve().parents[3]
 for path in (repo/'research/j0740/original_seven_inference',HERE,Path('/mnt/data/eos_finish/library_readback')):
  if path.is_dir() and str(path) not in sys.path:sys.path.insert(0,str(path))
 import original_seven_fullmass_integral as reference
 if sha(f38zip.read_bytes())!=F38_EXPECTED_SHA:raise EvidenceFailure('F38 native reconstructed source KDE ZIP SHA changed')
 curves={name:PchipInterpolator(np.array(v['source_selected_model_arrays']['mass_msun']),np.array(v['source_selected_model_arrays']['radius_eq_km']),extrapolate=False) for name,v in result.items()}
 obs={}
 with zipfile.ZipFile(f38zip) as z:
  for key in SIX_KEYS:
   surface,_=reference.load_surface(z,key)
   values={}
   for name,curve in curves.items():
    mlo,mhi=result[name]['accepted_numeric_source_mass_range_msun']
    lo=max(MASS_LO,mlo);hi=min(MASS_HI,mhi)
    if not lo<hi:raise EvidenceFailure(name+' no observed mass support')
    mass=np.linspace(lo,hi,n);r=curve(mass)
    allowed=reference.xpsi_source_support(mass,r)
    lik=surface(np.column_stack((mass,r)))
    lik=np.where(allowed,lik,0)
    score=float(simpson(reference.density(mass)*lik,x=mass))
    if not math.isfinite(score) or score<=0:raise EvidenceFailure(name+': invalid observation score')
    values[name]=score
   den=sum(values.values())
   obs[key]={'unnormalized_score':values,'discrete_seven_model_equal_prior_conditional_probabilities':{name:float(score/den) for name,score in values.items()}}
 summary={}
 for name in SEVEN:
  scores=np.array([o['unnormalized_score'][name] for o in obs.values()])
  weights=np.array([o['discrete_seven_model_equal_prior_conditional_probabilities'][name] for o in obs.values()])
  summary[name]={'conditional_seven_rotating_KDE_score_median':float(np.median(scores)),
                 'conditional_seven_rotating_KDE_probability_median':float(np.median(weights)),
                 'probability_min_max_six_KDE':[float(weights.min()),float(weights.max())],
                 'radius_2p073_km':result[name]['radius_at_original_direct_C_2p073_msun_km'],
                 'prior_mass_support_fraction':result[name]['source_radio_mass_prior_covered_fraction']}
 return dict(status='ROTATING_SEVEN_ORIGINAL_C_GR_SOURCE_KDE_CONDITIONAL_STATIC_SEQUENCE_REPLACED',
  metric='Seven discrete fixed original EOS RNS C rotation sequences, mass integrated over sampled increasing branch, six archived Salmi F38 prior-corrected 2D KDE surfaces, equal seven discrete prior, NOT source photon likelihood',
  input_F38_SHA256=F38_EXPECTED_SHA,
  radio_prior={'mean_msun':MASS_MU,'sigma_msun':MASS_SIGMA,'truncation_sigma':[-5,5]},
  source_NICER_XMM_2D_postprior_KDE_variants=list(SIX_KEYS),
  integration_n_per_curve=n,six_obs=obs,summary=summary,
  warnings=['Source RNS neutron stars have original low-P/ultracausal derivative issues and not certified physical.',
  'Finite RNS sampled increasing branch is not constant-J dynamical stability proof.',
  'Reconstructed F38 q/pi_eff from original posterior is not independently computed event-level X-PSI likelihood.',
  'WFF1/2 high-density source solver timed out beyond captured post-peak turning samples; no uncomputed stars assigned likelihood.',
  'Conditional weights are relative within only seven assumed original nuclear model labels; not universal astrophysical EOS probabilities.',
  'Radio mass enters only once; Amsterdam/Maryland photon samples not multiplied.'])

def run(root:Path,outdir:Path,f38zip:Path|None=None):
 result,origin,manifest=load_all(root)
 outdir.mkdir(parents=True,exist_ok=True)
 body={'schema':'J0740_SEVEN_ORIGINAL_RNS_ROTATING_GR_SAVED_C_RECOVERY_AND_MASSLINE_V1',
       'status':'SEVEN_NATIVE_ORIGINAL_FINITE_ROTATING_GR_MASS_SEQUENCES_RECONSTRUCTED_FROM_GITHUB_WITH_WFF_TIMEOUT_LOSS_ACCOUNTED',
       'CI_source_run_id':44565658458,
       'reused_original_Github_source_artifacts':manifest['artifacts'],
       'no_source_photon_tar_repeated':True,
       'physical_EOS_acceptance':'NOT_CERTIFIED',
       'all_seven_original_rotating_massline_C_sequences':result}
 if f38zip:
  body['rotating_mass_integrated_six_F38']=observed_rotating_KDE_inference(result,f38zip)
  body['status']='SEVEN_ORIGINAL_ROTATING_C_RNS_MASSLINE_AND_SIX_F38_KDE_DIAGNOSTICS_CALCULATED'
 dest=outdir/'J0740_seven_original_RNS_C_full_mass_recovery_20261119.json'
 dest.write_text(json.dumps(body,indent=2,sort_keys=True,allow_nan=False)+'\n')
 print(json.dumps({'status':body['status'],
     'C_source_counts':{k:v['raw_original_solver_count'] for k,v in result.items()},
     'WFF1_R_delta_m':result['WFF1']['massline_vs_exact_C_target_R_delta_m'],
     'WFF2_R_delta_m':result['WFF2']['massline_vs_exact_C_target_R_delta_m'],
     'coverage':{k:round(v['source_radio_mass_prior_covered_fraction'],6) for k,v in result.items()},
     'rotating_model_posteriors':{k:round(v['conditional_seven_rotating_KDE_probability_median'],6) for k,v in body.get('rotating_mass_integrated_six_F38',{}).get('summary',{}).items()},
     },indent=2))
 return body

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--archive-root',type=Path,default=HERE)
 p.add_argument('--outdir',type=Path,required=True);p.add_argument('--f38-zip',type=Path)
 args=p.parse_args();run(args.archive_root,args.outdir,args.f38_zip)
