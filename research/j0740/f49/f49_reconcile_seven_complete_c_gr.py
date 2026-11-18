"""F49: integrate seven F46/F48 FULL genuine mass grids; source locked.

F48 recovered original failed 2.0175 Msun WFF1 star with a new direct C-RNS
nested mass+spin root. F47's original WFF1-gap result remains immutable.
No extrapolation, final EOS physics or native X-PSI photon Bayesian posterior.
"""
from __future__ import annotations
import argparse,hashlib,json,sys,zipfile,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'f47'))
import f47_mass_integrated_source_likelihood as previous

F48_SHA='8217dddfa431d33105421b183b876be3b52cad16525c592459e7f90e8b19b786'
ORIGINAL_F47_RESULT_SHA='4e8f13eb5e4788dcf6106108e396df52abca0822f3775b08aa5b2821fd92d2ad'
# Six original F46 22-node directly measured star curves (WFF1 supplied by F48).
SIX_SOURCE_SHA={
 'APR4_EPP':'e3a6220e1406376faa6ffa6f21ce108954684a1066841d405644857cfa4937fc',
 'ENG':'98a94bffc29a60eb70211961678eb17abbad98414630ad11fb74353fbcd58ad8',
 'MPA1':'bf59ba4f0c3f43caf0942e748bf036fe80716131e7b4abe8b975d0f507dba4bf',
 'MS1':'e55ed502781abeb2ab2f78c85fcf7f6f3c143fb3feddb50a88b6849ecc9b8f94',
 'MS1B':'3aede27e6508f32af7c944fadf4c87a4867a333ea58b3d40617452bda3cac774',
 'WFF2':'cb0f3e52bcfe2f17566934ab9bd4bf6d75d68e9aa2f6cc282656d9eba9e77798'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def restore_wff1(f48, curves_dir):
 if sha(f48)!=F48_SHA:raise ValueError('PINNED_F48_REAL_C_GR_ARTIFACT_SHA_MISMATCH')
 with zipfile.ZipFile(f48) as z:
  if z.testzip() is not None:raise ValueError('F48_ZIP_CRC_MISMATCH')
  report=json.loads(z.read('F48_WFF1_real_direct_rescue.json'))
  corrected=z.read('WFF1_fixed_spin_direct_curve_F48_recovered.json')
  rec=json.loads(corrected)
 if report['status']!='DIRECT_C_GR_WFF1_MISSING_MASS_ROOT_RECOVERED_NOT_PHYSICAL_STABILITY':
  raise ValueError('F48_RESCUE_NOT_GENUINELY_SOLVED')
 star=report['root']
 if not (abs(star['mass_msun']-2.0175)<1e-4 and abs(star['spin_hz']-346.536369)<.01
         and abs(star['radius_eq_km']-rec['roots']['2.0175']['radius_eq_km'])<1e-10):
  raise ValueError('F48_GENUINE_C_GR_ROOT_DOES_NOT_MATCH_CURVE')
 if rec['status']!='COMMON_WINDOW_GRID_COMPLETE_NOT_GLOBAL_STABILITY_PROOF' or rec['successful_common_targets']!=22:
  raise ValueError('F48_WFF1_FULL_COMMON_WINDOW_ROOTS_MISSING')
 curves_dir.mkdir(parents=True,exist_ok=True)
 out=curves_dir/'WFF1_fixed_spin_direct_curve.json';out.write_bytes(corrected)
 for name,h in SIX_SOURCE_SHA.items():
  if sha(curves_dir/(name+'_fixed_spin_direct_curve.json'))!=h:
   raise ValueError('F46_SIX_ORIGINAL_C_GR_SOURCE_SHA_MISMATCH:'+name)
 return report,sha(out)


F47_ALLOWED_BACKEND_STATUSES=frozenset({
 'SEVEN_CONDITIONAL_COMMON_WINDOW_INTEGRALS_WITH_ONE_WFF1_INTERNAL_ROOT_GAP_NOT_FULL_BAYES',
 'SEVEN_CONDITIONAL_COMMON_WINDOW_INTEGRALS_AFTER_F48_WFF1_ROOT_RESCUE_NOT_FULL_BAYES',
})


def validate_backend_state(result):
 # F47 backend evolved after the actual F48 RNS rescue. Both represent
 # conditional F38 source likelihoods, but F49 requires an exact COMPLETE
 # 7x22 C/GR mass grid regardless of which upstream receipt label it emits.
 if result.get('status') not in F47_ALLOWED_BACKEND_STATUSES:
  raise ValueError('UNEXPECTED_F47_BACKEND_RESULT_STATUS:'+repr(result.get('status')))
 expected={name:[] for name in previous.EOS}
 if result.get('missing_direct_RNS_targets')!=expected:
  raise ValueError('F49_BACKEND_MISSING_OR_UNEXPECTED_DIRECT_C_RNS_MASS_TARGET')
 return result['status']


def reconcile(result,prior, f48_report):
 validate_backend_state(result)
 if len(result['surfaces'])!=6 or set(result['curve_sha256'])!=set(previous.EOS):
  raise ValueError('SEVEN_SOURCE_F38_INTEGRALS_MISSING')
 old=prior['surfaces'];changed={};unchanged_max=0.
 for k,v in result['surfaces'].items():
  changed[k]={}
  for name,integral in v['seven_integrals'].items():
   val=integral['conditional_on_common_window_source_Z_ratio']
   ref=old[k]['seven_integrals'][name]['conditional_on_common_window_source_Z_ratio']
   delta=100*(val/ref-1) if ref>0 else None
   changed[k][name]=delta
   if name!='WFF1':unchanged_max=max(unchanged_max,abs(val-ref))
 if unchanged_max>1e-12:raise ValueError('NON_WFF1_SOURCE_INTEGRAL_CHANGED_WITHOUT_DATA_CHANGE')
 if not all(0<changed[k]['WFF1']<.3 for k in changed):
  raise ValueError('WFF1_DIRECT_STAR_RESCUE_INTEGRAL_CHANGE_UNEXPECTED')
 if not all(x['highest_conditional_common_window_model']=='MPA1' for x in result['surfaces'].values()):
  raise ValueError('SIX_F38_GRID_ORDER_CHANGED_REQUIRES_REVIEW')
 result.update({
  'schema':'J0740_F49_SEVEN_ALL_DIRECT_22_NODE_COMMON_MASS_SOURCE_INTEGRALS_v1',
  'status':'F49_SEVEN_22_NODE_DIRECT_RNS_MASS_INTEGRALS_VALIDATED_NOT_FULL_NUCLEAR_EOS_BAYES',
  'F46_original_WFF1_failed_C_root':'PRESERVED_IN_SOURCE_ARTIFACT_44286241129',
  'F48_direct_C_GR_WFF1_recovery_sha256':F48_SHA,
  'F48_real_direct_rescued_mass_2p0175':f48_report['root'],
  'F49_all_seven_22_real_direct_star_mass_nodes':True,
  'F49_all_seven_full_rising_interval_mass_grid_completed':True,
  'F49_old_F47_vs_now_relative_percent_by_surface_and_new_model':changed,
  'F49_non_WFF1_max_difference':unchanged_max,
  'F49_real_WFF1_correction_max_pct':max(abs(v['WFF1']) for v in changed.values()),
  'F49_nuclear_EOS_physical_family_verified':'NOT_ESTABLISHED',
  'F49_global_rotating_fixed_J_stability':'NOT_ESTABLISHED',
  'F49_source_derived_F38_not_native_photon_XPSI':True,
  'full_seven_model_Bayes_posterior':'NOT_RUN',
  'mass_uncovered_prior_likelihood':'UNKNOWN_NOT_ASSUMED_ZERO',
  'original_F46_failed_matrix_independent':'RETAINED_UNALTERED',
  'F49_memo':'All original 7 EOS raw nuclear theories are NOT this nonunique new seven barotrope family; L/Z is conditional [1.95,2.10]M_sun and model-prior choice is unvalidated'})
 result['F46_original_CI_status']='F46_INITIAL_SINGLE_WFF1_FAILURE_PRESERVED; NEW_F48_DIRECT_C_GR_STAR_RECOVERED_AND_CHECKED'
 result['missing_direct_RNS_targets']={name:[] for name in previous.EOS}
 return result


def run(f38,f44,f48,curves_dir,old_f47,out):
 if sha(old_f47)!=ORIGINAL_F47_RESULT_SHA:raise ValueError('PINNED_F47_ORIGINAL_SCIENCE_RESULT_SHA_MISMATCH')
 orig=json.loads(old_f47.read_text())
 resc,rev_sha=restore_wff1(f48,curves_dir)
 tmp=out.with_name('F49_source_F47_backend_intermediate.json')
 j=previous.run(f38,f44,curves_dir,tmp)
 print('F49_BACKEND_DIAGNOSTIC_STATUS',repr(j.get('status')), 'SURFACES',len(j.get('surfaces',{})),flush=True)
 j=reconcile(j,orig,resc)
 j['source_complete_WFF1_recovered_curve_sha256']=rev_sha
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(j,sort_keys=True,indent=2,allow_nan=False)+'\n')
 print(json.dumps({'status':j['status'],'all_seven_direct_nodes':j['F49_all_seven_22_real_direct_star_mass_nodes'],
                   'max_abs_WFF1_change_pct':j['F49_real_WFF1_correction_max_pct'],
                   'first_each_surface':[x['highest_conditional_common_window_model'] for x in j['surfaces'].values()]},sort_keys=True))
 return j


def main():
 p=argparse.ArgumentParser()
 for n in ['f38','f44','f48','curves-dir','old-f47','out']:p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args()
 run(a.f38,a.f44,a.f48,a.curves_dir,a.old_f47,a.out)
if __name__=='__main__':main()
