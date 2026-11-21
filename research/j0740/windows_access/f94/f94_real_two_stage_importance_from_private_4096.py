"""F94 valid adaptive two-stage importance evidence on REAL native X-PSI at fixed M,R.
V1 is stage 1 and V2 proposal depends on stage 1, so NEVER use adaptive balance MIS as certified.
Instead keep original correct per-proposal importance weights: I = .5*(mean_V1 weights + mean_V2 weights).
Independent of *each model's own acceptance* and not a seven-EOS Bayes factor.
"""
import hashlib,json,math
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
R=Path(r'C:\Users\User\Documents\Codex\2026-11-08\codex-psr-j0740-6620-ara-tirmasina\evidence\native_photon')
W=Path(r'C:\Users\User\AppData\Local\SentinelX\workspace')
V2=W/'J0740_F91_V2_fresh_native_validation_20261121'
OUT=W/'F94_15p26_two_stage_valid_native_importance_4096_20261121.json'
ss1=(211301,211303,211307,211311)
ss2=(211401,211403,211407,211411)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
stages=[]
rows=[]
for kind,seeds in [('V1',ss1),('V2',ss2)]:
 s=[]
 for seed in seeds:
  f=R/f'MR_anchor_2_tailpatch_seed_{seed}_512_local.npz' if kind=='V1' else V2/f'MR15p26_F91V2_seed_{seed}_512_native.npz'
  with np.load(f,allow_pickle=False) as d:
   lw=np.asarray(d['logweights'],float)
   assert len(lw)==512 and not np.isnan(lw).any()
  li=float(logsumexp(lw)-math.log(512))
  s.append({'seed':seed,'logI':li,'npz_SHA256':sha(f),'finite_draws':int(np.isfinite(lw).sum()),
    'ESS':float(np.exp(2*logsumexp(lw)-logsumexp(2*lw))),
    'maxW':float(np.exp(np.max(lw)-logsumexp(lw)))})
  rows.append({'stage':kind,'seed':seed,'logweights':lw})
 logIs=np.array([x['logI'] for x in s])
 ll=float(logsumexp(logIs)-math.log(4))
 se_relative=float(np.std(np.exp(logIs-ll),ddof=1)/math.sqrt(4))
 stages.append({'stage':kind,'seed_reports':s,'draws':2048,'logI_stage':ll,
    'relative_standard_error_from_four_scrambled_QMC_replicates':se_relative,
    'max_replicate_logI_minus_min':float(np.ptp(logIs))})
center=max(x['logI_stage'] for x in stages)
means=np.array([math.exp(x['logI_stage']-center) for x in stages])
avg=float(means.mean())
logI=center+math.log(avg)
se_total_scaled=math.sqrt(sum((means[i]*stages[i]['relative_standard_error_from_four_scrambled_QMC_replicates'])**2 for i in range(2)))/2
ser=se_total_scaled/avg
ll=np.concatenate([x['logweights'] for x in rows])
lognorm=logsumexp(ll)
w=np.exp(ll-lognorm)
res={'schema':'J0740_F94_TWO_STAGE_SOURCE_NATIVE_VALID_IMPORTANCE_V1',
  'method':'1/2*mean_2048_Stage1 importance weights q1 + 1/2*mean_2048_Stage2 importance weights q2, where q2 was chosen based on earlier Stage1 but new Stage2 seeds are independent, allowing conditional unbiasedness',
  'correction':'Do NOT treat cross-density balance MIS F93 as unbiased; F94 uses ONLY original q_i denominators, no adaptive retroactive reweight',
  'target':[2.073,15.26],'total_real_native_photon_model_draws_reused':4096,
  'new_native_photon_calls':0,'normalized_support':0.24947354926879406,
  'stages':stages,'logI_two_stage_point_estimate':float(logI),
  'estimated_relative_standard_error_RQMC':ser,
  'approx_logI_one_standard_error':ser,
  'full_combined_weight_ESS_diagnostic_not_prespecified_acceptance':float(1/(w@w)),
  'combined_max_normalized_weight_diagnostic':float(w.max()),
  'original_independent_seed_acceptance':{'V1':'FAIL','V2':'FAIL'},
  'source_model':{'V1':'source model fixed, code pinned in F91 receipt','V2':'be896b89f38736dfa41eb296853ba021c6248dd389dacc88f6ecbfaff755c010'},
  'source_model_physics_changed_between_stages':False,
  'caveats':'4 RQMC replicates per stage, approximate empirical SE; distinct original per-seed ESS/maxW gates failed; NOT convergence proof, NOT seven EOS photon Bayes',
  'full_MR_EOS_Bayes':'NOT_RUN'}
assert all(len(x['seed_reports'])==4 for x in stages)
assert len(ll)==4096
assert res['estimated_relative_standard_error_RQMC']>0
OUT.write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf8')
print(json.dumps({'receipt_sha256':sha(OUT),'combined_logI':logI,'estimated_relSE':ser,'combined_ESS':res['full_combined_weight_ESS_diagnostic_not_prespecified_acceptance'],'maxW':res['combined_max_normalized_weight_diagnostic'],'stages':[{'name':x['stage'],'logI':x['logI_stage'],'relSE':x['relative_standard_error_from_four_scrambled_QMC_replicates'],'spread':x['max_replicate_logI_minus_min']} for x in stages]}))

