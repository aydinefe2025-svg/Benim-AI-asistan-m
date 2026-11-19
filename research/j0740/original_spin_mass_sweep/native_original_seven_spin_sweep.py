#!/usr/bin/env python3
"""Source-locked SEVEN original nuclear EOS sequences of true RNS-C rotating GR stars.

No 12.9GB NICER re-read, no MPA1 F62 target mass re-run; fresh nearby C models
needed to obtain R_eq(M, spin). 196 knots raw-source-representative table.
The first sampled mass-increasing branch is an approximate numerical diagnostic,
NOT a global constant-J physical stability certificate or native XPSI evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
import subprocess
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.stats import truncnorm

REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'research/j0740/rotating_gr'))
from jester_to_rns import from_jester_npz,write_rns,C,G
from rns_benchmark import OBSERVED_SPIN_HZ,RNS_COMMIT,sha256_file
from axis_ratio_rns import run_rns_at_spin_with_ratio_fallback

SEVEN={
 'APR4_EPP':'639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88',
 'ENG':'702da3ddf7c10b0091af5d8c0d576a9e9a85a85726849a2860bdd8ef3643f953',
 'MPA1':'0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22',
 'MS1':'531530be6253984622f667f454f825ccd13fa4e8960a1411aefe5dd7ea5ff3ad',
 'MS1B':'7a3302e8f2541469fc9ba26dbe52f97b1c8696b71864a208ca43ca7f5cde984c',
 'WFF1':'119b8a25435faeddf00f5d3638f3ff2ff00283ce60caacc24cc37c6e2e030ed3',
 'WFF2':'eb08edc3723fc32d428b3dc3b21aa612dad8a3bdb5da6246faedbb7ed65683ae',
}
F61_SHA='7b2cbcf6df2dc55d33046d9af587dba179dcb2ec77bad0395e628742479cce0a'
PREVIOUS_DIRECT_C_M2073={
 'APR4_EPP':10.754850283,'ENG':11.587725250,'MPA1':12.533295930,
 'MS1':15.258445346,'MS1B':14.985468809,'WFF1':9.975731674,'WFF2':10.623929893}
MASS=2.073
NUM_MODELS=48
LOW_FACTOR=.44
HIGH_FACTOR=2.12
CURVE_MASS_VALIDATION_TOL_KM=.050

def seed_source(source,f61,model):
 if model not in SEVEN:raise ValueError('NOT AN ORIGINAL SEVEN EOS LABEL')
 if sha256_file(source)!=SEVEN[model]:raise ValueError('NPZ ORIGINAL JESTER SOURCE HASH MISMATCH')
 if sha256_file(f61)!=F61_SHA:raise ValueError('F61 original LALSuite stationary stars source SHA mismatch')
 obj=json.loads(f61.read_text())
 if obj['results'][model]['source_npz_sha256']!=SEVEN[model]:raise ValueError('Original source disconnected from LALSuite statics')
 star=obj['results'][model]['stars']['2.073']
 if star['status']!='DIRECT_NATIVE_LAL_TOV_WITH_SOURCE_MR_CROSSCHECK':raise ValueError('F61 root not direct')
 with np.load(source,allow_pickle=False) as npz:
  p,e=np.asarray(npz['p'],float),np.asarray(npz['e'],float)
  cs2=np.asarray(npz['cs2'],float)
 if not np.all(np.diff(p)>0) or not np.all(np.isfinite(e)):
  raise ValueError('original source thermo invalid')
 pc=G/C**4*float(star['central_pressure_si_pa'])
 rho=float(np.exp(np.interp(math.log(pc),np.log(p),np.log(e)))*C*C/G*1.e-3)
 return rho,{'native_F61_static_target_R_km':star['radius_km'],
             'original_nonpositive_cs2_nodes':int(np.sum(cs2<=0)),
             'original_superluminal_cs2_nodes':int(np.sum(cs2>1)),
             'source_original_e_nonincreasing_edges':int(np.sum(np.diff(e)<=0)),
             'original_baryon_n_proxy_is_not_firstlaw_calibration':True,
             'original_global_EOS_physical_cert':'NOT_ESTABLISHED'}

def choose_first_mass_increasing_branch(stars):
 a=sorted(stars,key=lambda t:t['central_energy_density_g_cm3'])
 if len(a)<12:raise ValueError('too few direct C rotating stars for interpolation')
 masses=np.array([v['mass_msun'] for v in a])
 peak=int(np.argmax(masses));prefix=a[:peak+1]
 selected=[];rejected=[]
 for x in prefix:
  m=x['mass_msun']
  if not selected or m>selected[-1]['mass_msun']+.00001:selected.append(x)
  else:rejected.append({'density':x['central_energy_density_g_cm3'],'mass':m,'reason':'monotone mass grid selection; not dynamical stability certificate'})
 if len(selected)<10 or not selected[0]['mass_msun']<MASS<selected[-1]['mass_msun']:
  raise ValueError('sampled first increasing branch does not bracket measured 2.073 mass')
 return selected,peak,rejected

def original_late_timeout_after_witnessed_mass_peak(stars):
 """True only after enough REAL direct C stars bracket M=2.073 and
 the sampled maximum has at least two later, measurably lower mass stars.
 This is a NUMERICAL sampled branch gate, NEVER a constant-J physics proof.
 """
 if len(stars)<30:
  return False
 m=np.asarray([x['mass_msun'] for x in sorted(stars,key=lambda x:x['central_energy_density_g_cm3'])])
 if not np.all(np.isfinite(m)) or not m.min()<MASS<m.max():
  return False
 pk=int(np.argmax(m))
 return len(m)-pk-1>=2 and m[pk]-m[-1]>=.003

def run_model(source,f61,rns,eos,out):
 out.mkdir(parents=True,exist_ok=True)
 fname=out/f'{eos}_original_346Hz_RNS_C_mass_sequence_20261119.json'
 result={'schema':'J0740_ORIGINAL_SEVEN_EOS_GENUINE_ROTATING_RNS_C_346HZ_MASS_SWEEP_V1',
         'EOS':eos,'status':'REAL_C_SWEEP_NOT_YET_COMPLETE',
         'source_original_npz_sha256':sha256_file(source) if source.exists() else None,
         'F61_source_sha256':sha256_file(f61) if f61.exists() else None,
         'RNS_solver_sha256':sha256_file(rns) if rns.exists() else None,
         'RNS_source_commit':RNS_COMMIT,'JESTER_source_commit':'e6768650ce992abfd1153a6833857572fe5cd230',
         'requested_spin_hz':OBSERVED_SPIN_HZ,'original_EOS_modified':False,
         'raw_C_rotating_stars':[],'failed_source_C_evaluations':[],
         'model_physical_EOS_admissibility':'NOT_ESTABLISHED',
         'native_XPSI_photon_likelihood':'NOT_RUN','full_original_EOS_Bayes':'NOT_RUN'}
 def save():fname.write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n')
 try:
  anchor,flags=seed_source(source,f61,eos)
  result.update({'static_F61_based_central_energy_density_g_cm3':anchor,'original_source_flags':flags})
  rows,info=from_jester_npz(source,points=196)
  table=out/f'{eos}_source_original_196pts_SI_converted.rns'
  write_rns(table,rows)
  result['RNS_source_input_table_sha256']=sha256_file(table)
  result['resampling_info']=info
  hi=min(float(rows[-1,0])*.975,anchor*HIGH_FACTOR)
  lo=max(float(rows[0,0])*1.05,anchor*LOW_FACTOR)
  if not 0<lo<anchor<hi:raise ValueError('original EOS density domain fails sampled branch request')
  energies=np.geomspace(lo,hi,NUM_MODELS)
  save()
  for i,ec in enumerate(energies):
   try:
    z=run_rns_at_spin_with_ratio_fallback(rns,table,central_density=float(ec),spin_hz=OBSERVED_SPIN_HZ)
    a={k:v for k,v in z.items() if k not in ('raw_stdout_tail','axis_ratio_bisection_trace')}
    if abs(a['spin_hz_reported']-OBSERVED_SPIN_HZ)>.25 or not 8<a['radius_eq_km']<20:
      raise ValueError('physical C star mass/frequency/radius tolerance')
    result['raw_C_rotating_stars'].append(a)
   except (RuntimeError,ValueError,TimeoutError,OverflowError,subprocess.TimeoutExpired) as err:
    result['failed_source_C_evaluations'].append({'central_density':float(ec),'type':type(err).__name__,'message':str(err)[:260]})
    if isinstance(err,subprocess.TimeoutExpired):
     if not original_late_timeout_after_witnessed_mass_peak(result['raw_C_rotating_stars']):
      raise ValueError('RNS_HIGH_DENSITY_TIMEOUT_BEFORE_WITNESSED_TURNOVER_OR_MASS_SUPPORT') from err
     result['source_late_highdensity_timeout']={
       'density_g_cm3':float(ec),'duration_seconds':err.timeout,
       'raw_direct_C_stars_before_timeout':len(result['raw_C_rotating_stars']),
       'uncomputed_higher_density_grid_points':len(energies)-i-1,
       'reason':'Late solver timeout after measured postpeak; do not fabricate skipped stars or continuous stability'}
     print(eos,'RECOVERED_REAL_C_BRANCH_AFTER_POSTPEAK_TIMEOUT',len(result['raw_C_rotating_stars']),flush=True)
     save()
     break
   if i%5==0:
    print(eos,i,'of',len(energies),'direct C models',len(result['raw_C_rotating_stars']),'fail',len(result['failed_source_C_evaluations']),flush=True)
    save()
  valid,peak,rejected=choose_first_mass_increasing_branch(result['raw_C_rotating_stars'])
  m=np.asarray([x['mass_msun'] for x in valid]);r=np.asarray([x['radius_eq_km'] for x in valid])
  interp=PchipInterpolator(m,r,extrapolate=False)
  r073=float(interp(MASS))
  delta=r073-PREVIOUS_DIRECT_C_M2073[eos]
  result['C_sequence_reconstructed_mass_2p073_R_eq_km']=r073
  result['source_previous_exact_2p073_true_C_R_eq_km']=PREVIOUS_DIRECT_C_M2073[eos]
  result['sequence_minus_independent_source_direct_C_R_km']=delta
  result['sequence_target_radius_within_50m']=abs(delta)<=CURVE_MASS_VALIDATION_TOL_KM
  result['mass_increasing_branch_C_stars']=valid
  result['mass_increasing_branch_count']=len(valid)
  result['sampled_mass_peak_Msun']=max(x['mass_msun'] for x in result['raw_C_rotating_stars'])
  result['sampled_peak_index_sorted_by_central_energy']=peak
  result['nonmonotone_discarded_numeric_models']=rejected
  result['first_increasing_C_mass_range_Msun']=[float(m.min()),float(m.max())]
  result['radio_prior_mass_covered_by_sampled_branch']=float(truncnorm.cdf(min(2.082+5*.0703,m.max()),-5,5,loc=2.082,scale=.0703)-truncnorm.cdf(max(2.082-5*.0703,m.min()),-5,5,loc=2.082,scale=.0703))
  result['direct_C_mass_sequence_interpolation_NOT_EOS_physical_stability_cert']=True
  if not result['sequence_target_radius_within_50m']:
    raise ValueError('RNS C mass sequence does not reproduce independent C target radius <50m')
  result['status']=('ORIGINAL_EOS_ROTATING_SAMPLED_C_BRANCH_AFTER_HIGH_DENSITY_TIMEOUT_NOT_PHYSICALLY_CERTIFIED'
                    if result.get('source_late_highdensity_timeout') else
                    'ORIGINAL_EOS_ROTATING_FULL_C_SEQUENCE_SAMPLED_AND_CROSSCHECKED_NOT_PHYSICALLY_CERTIFIED')
 except Exception as exc:
  result['status']='NUMERICAL_RECONSTRUCTION_NOT_ACCEPTED'
  result['failing_gate']={'type':type(exc).__name__,'message':str(exc)[:1200]}
 save()
 print(json.dumps({'model':eos,'status':result['status'],'all_C_stars':len(result['raw_C_rotating_stars']),
    'mass_span':result.get('first_increasing_C_mass_range_Msun'),'mass_prior_covered':result.get('radio_prior_mass_covered_by_sampled_branch'),
    'independent_C_check_km':result.get('sequence_minus_independent_source_direct_C_R_km'),
    'failed':len(result['failed_source_C_evaluations'])}),flush=True)
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--f61',type=Path,required=True);p.add_argument('--rns',type=Path,required=True);p.add_argument('--model',choices=sorted(SEVEN),required=True);p.add_argument('--outdir',type=Path,required=True)
 a=p.parse_args();v=run_model(a.source,a.f61,a.rns,a.model,a.outdir)
 if v['status'] not in {
  'ORIGINAL_EOS_ROTATING_FULL_C_SEQUENCE_SAMPLED_AND_CROSSCHECKED_NOT_PHYSICALLY_CERTIFIED',
  'ORIGINAL_EOS_ROTATING_SAMPLED_C_BRANCH_AFTER_HIGH_DENSITY_TIMEOUT_NOT_PHYSICALLY_CERTIFIED'}:raise SystemExit(2)
