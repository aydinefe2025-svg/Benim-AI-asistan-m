#!/usr/bin/env python3
"""Independent source-sha-locked replay of 42 original rotating-GR F38 massline integrals.
The CI witnesses derive from full 2D authentic F38 file. Full 2D source is
included in offline ZIP and used in local direct computation, not re-fetched in CI.
"""
from __future__ import annotations
import argparse,base64,hashlib,io,json,math,sys
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
from scipy.interpolate import PchipInterpolator
import recover_native_seven_rotating as original

HERE=Path(__file__).resolve().parent

def verify(root:Path,truth:Path,out:Path):
 sources,_,orig_manifest=original.load_all(root)
 obs=json.loads(truth.read_text())
 if obs['status']!='SEVEN_ORIGINAL_ROTATING_C_RNS_MASSLINE_AND_SIX_F38_KDE_DIAGNOSTICS_CALCULATED':
  raise original.EvidenceFailure('not verified full F38 original-source 7-EOS result')
 if obs['CI_source_run_id']!=44565658458 or set(obs['all_seven_original_rotating_massline_C_sequences'])!=set(original.SEVEN):
  raise original.EvidenceFailure('wrong observed direct C source evidence')
 for model in original.SEVEN:
  expected=obs['all_seven_original_rotating_massline_C_sequences'][model]
  actual=sources[model]
  if abs(expected['massline_vs_exact_C_target_R_delta_m']-actual['massline_vs_exact_C_target_R_delta_m'])>1e-9:
   raise original.EvidenceFailure('full F38 result not based on source C GR data')
 witnesses=json.loads((root/'witness/F38_rotating_massline_witness_manifest.json').read_text())
 if witnesses['source_2d_F38_archive_SHA256']!=original.F38_EXPECTED_SHA or set(witnesses['models'])!=set(original.SEVEN):
  raise original.EvidenceFailure('F38 source 2D archive pin changed')
 repo=Path(__file__).resolve().parents[3]
 for path in [repo/'research/j0740/original_seven_inference',Path('/mnt/data/eos_finish/library_readback')]:
  if path.is_dir() and str(path) not in sys.path:sys.path.insert(0,str(path))
 import original_seven_fullmass_integral as likelihood_source
 maxrel=0.0;count=0;source_witnesses={}
 for label in original.SEVEN:
  item=witnesses['models'][label]
  if item['source_C_artifact_zip_sha256']!=orig_manifest['artifacts'][label]['zip_sha256']:
   raise original.EvidenceFailure('witness source GR archive mismatch')
  raw=base64.b64decode((root/'witness'/item['file']).read_text().strip(),validate=True)
  if hashlib.sha256(raw).hexdigest()!=item['decoded_npz_sha256']:
   raise original.EvidenceFailure('original F38 source witness bytes changed')
  with np.load(io.BytesIO(raw),allow_pickle=False) as x:
   m=np.asarray(x['mass_msun'],float);r=np.asarray(x['radius_eq_km'],float)
   L=np.asarray(x['relative_likelihood_on_original_F38'],float)
   allowed=np.asarray(x['support_mask'],bool)
  if item['masses_n']!=len(m) or L.shape!=(6, len(m)) or m.ndim!=1 or not np.all(np.diff(m)>0):
   raise original.EvidenceFailure('invalid F38 source line witness shape')
  original_line=sources[label]['source_selected_model_arrays']
  interp=PchipInterpolator(np.asarray(original_line['mass_msun']),np.asarray(original_line['radius_eq_km']),extrapolate=False)
  if np.max(abs(r-interp(m)))>1e-11:raise original.EvidenceFailure('witness radius does not follow original C star sequence')
  if not np.array_equal(allowed,likelihood_source.xpsi_source_support(m,r)):
   raise original.EvidenceFailure('witness prior support different from F38 source geometry')
  if np.any(~np.isfinite(L)) or np.min(L)<0 or np.any(L[:,~allowed]!=0):
   raise original.EvidenceFailure('F38 likelihood outside original prior support')
  for i,key in enumerate(original.SIX_KEYS):
   real=float(simpson(likelihood_source.density(m)*L[i],x=m))
   orig=float(obs['rotating_mass_integrated_six_F38']['six_obs'][key]['unnormalized_score'][label])
   if not (np.isfinite(real) and real>0 and np.isfinite(orig) and orig>0):
    raise original.EvidenceFailure('nonpositive original massline source score')
   relative=abs(real/orig-1)
   if relative>=1.e-5:raise original.EvidenceFailure(f'F38 rotating 1D witness vs full true 2D integration drift {label} {key} {relative}')
   maxrel=max(maxrel,relative);count+=1
  source_witnesses[label]={'actual_direct_C_source_count':sources[label]['raw_original_solver_count'],'source_witness_sha256':item['decoded_npz_sha256'],
      'source_model_independent_C_radius_delta_metres':sources[label]['massline_vs_exact_C_target_R_delta_m'],
      'recover_high_density_timeout_without_fake_stars':sources[label]['high_density_solver_timeout_recovered']}
 for key,o in obs['rotating_mass_integrated_six_F38']['six_obs'].items():
  assert abs(sum(o['discrete_seven_model_equal_prior_conditional_probabilities'].values())-1)<1e-12
 if count!=42:raise original.EvidenceFailure('not all 42 rotating original EOS scores checked')
 result={'status':'ALL_SEVEN_ORIGINAL_ROTATING_C_GR_AND_42_REAL_F38_WITNESS_INTEGRALS_CI_PASS',
  'provenance_original_source_run_id':44565658458,'seven_real_RNS_C_source_stars_total':sum(x['raw_original_solver_count'] for x in sources.values()),
  'WFF1_WFF2_numerical_high_density_timeouts_recovered_without_RNS_reruns':True,
  'f38_full_2D_original_ZIP_sha256':original.F38_EXPECTED_SHA,
  'witness_based_1D_CI_not_full_2D_source_recalculation':True,
  'source_native_gamma_photon_XPSI_re_inference':'NOT_RUN',
  'physical_EOS_microphysics_global_cert':'NOT_CERTIFIED',
  'score_count':count,'worst_relative_original_F38_2D_integral_replay_difference':maxrel,
  'source_witnesses':source_witnesses}
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 print(json.dumps({k:result[k] for k in ('status','seven_real_RNS_C_source_stars_total','score_count','worst_relative_original_F38_2D_integral_replay_difference')},sort_keys=True))
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--archive-root',type=Path,default=HERE);p.add_argument('--full-2d-result',type=Path,default=HERE/'out/J0740_seven_original_RNS_C_full_mass_recovery_20261119.json');p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();verify(a.archive_root,a.full_2d_result,a.out)
