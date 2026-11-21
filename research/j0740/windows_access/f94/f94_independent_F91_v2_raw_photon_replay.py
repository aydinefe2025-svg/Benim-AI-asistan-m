#!/usr/bin/env python3
"""Independent four-seed F91 V2 raw NPZ+JSONL replay. No photon likelihood calls."""
from pathlib import Path
import json,hashlib,math,sys
import numpy as np
from scipy.special import ndtri,logsumexp
from scipy.stats import qmc,truncnorm
ROOT=Path(r'C:\Users\User\Documents\Codex\2026-11-08\codex-psr-j0740-6620-ara-tirmasina')
NATIVE=ROOT/'native_prior'
sys.path.insert(0,str(NATIVE))
from temperature_coupling import Coupling,TransportProposal
from conditional_proposal import condition
from conditional_tail_patch import ConditionalTailPatchedProposal
from normalized_source_prior import RLO,RHI
from support_normalization import nuisance_acceptance
W=Path(r'C:\Users\User\AppData\Local\SentinelX\workspace')
DESIGN=W/'J0740_15p26_V2_frozen_after_211307_FAIL_20261121.json'
RUN=W/'J0740_F91_V2_fresh_native_validation_20261121'
OUT=W/'F91_V2_independent_native_four_seed_replay_20261121.json'
EXPECTED='82f0393ca7389ae68d1dc5c751d7ff1b24ece790a16a284f22f5155b7ec25a2f'
MODEL_SHA='be896b89f38736dfa41eb296853ba021c6248dd389dacc88f6ecbfaff755c010'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(DESIGN)==EXPECTED
d=json.loads(DESIGN.read_text(encoding='utf8'))
assert d['NEW_INDEPENDENT_VALIDATION_SEEDS']==[211401,211403,211407,211411]
fixed=ndtri([truncnorm.cdf(2.073,-5,5,loc=2.082,scale=.0703),(15.26-RLO)/(RHI-RLO)])
src=ROOT/'evidence'/'native_photon'/'temperature_transport_K48_local.npz'
assert sha(src)==d['underlying_original_flow_sha256']
with np.load(src,allow_pickle=False) as f:
 flow=Coupling(f['coupling_shift'],f['coupling_scale'],f['coupling_coef'])
 w,mu,cov=condition(f['weights'],f['means'],f['covs'],fixed)
base=TransportProposal(w,mu,cov,flow,fixed=fixed)
q=ConditionalTailPatchedProposal(base,flow,fixed,
    np.asarray(d['centers_in_unit_jacobian_transport_coordinates']),
    np.asarray(d['covariances']),epsilon=d['epsilon'],df=d['df'])
SUP=nuisance_acceptance()
assert abs(SUP-.24947354926879406)<1e-13
report={'schema':'J0740_F91_V2_INDEPENDENT_SOURCE_NATIVE_FOUR_SEED_REAL_REPLAY_V1',
    'frozen_design_sha256':EXPECTED,'physical_source_model_sha256':MODEL_SHA,
    'model_source_evaluations_run_by_this_audit':0,
    'unchanged_original_source_gates':d['FIXED_PRIOR_ACCEPTANCE_GATES'],
    'target':[2.073,15.26],'raw_private_files_remain_windows':True,
    'seed_results':[],'partial_seeds':[],'pending_seeds':[],'full_MR_Bayes':'NOT_RUN'}
for seed in d['NEW_INDEPENDENT_VALIDATION_SEEDS']:
    u=qmc.Sobol(17,scramble=True,seed=seed).random_base2(9)
    z=q.from_unit(u)
    lq=q.logpdf(z)
    raw=RUN/f'MR15p26_F91V2_seed_{seed}_evals.jsonl'
    npz=RUN/f'MR15p26_F91V2_seed_{seed}_512_native.npz'
    summ=RUN/f'MR15p26_F91V2_seed_{seed}_summary.json'
    if not raw.is_file():
        report['pending_seeds'].append(seed)
        continue
    lines=raw.read_text(encoding='utf8').splitlines()
    events=[json.loads(line) for line in lines if line.strip()]
    assert 0<len(events)<=512
    for i,e in enumerate(events):
        assert e['index']==i and e['seed']==seed
        assert e['design_sha256']==EXPECTED and e['source_model_sha256']==MODEL_SHA
        assert e['fixed_mass_radius']==[2.073,15.26]
        assert np.array_equal(z[i],np.asarray(e['z'],float))
        if e['logL'] is not None:assert math.isfinite(e['logL'])
    if not (npz.is_file() and summ.is_file()):
        report['partial_seeds'].append({'seed':seed,'rows_source_matched':len(events),'raw_sha256_now_not_final':sha(raw)})
        continue
    assert len(events)==512,('F91V2_PARTIAL_EVENT_LIST_WITH_COMPLETED_NPZ',seed)
    sr=json.loads(summ.read_text(encoding='utf8'))
    with np.load(npz,allow_pickle=False) as f:
        zsrc=np.asarray(f['z'],float);lwsrc=np.asarray(f['logweights'],float);lqsrc=np.asarray(f['logq'],float)
    assert np.array_equal(z,zsrc) and np.max(abs(lq-lqsrc))<1e-12
    logw=np.full(512,-np.inf)
    for i,e in enumerate(events):
        if e['logL'] is not None:
            logw[i]=float(e['logL'])-.5*(13*math.log(2*math.pi)+float(z[i]@z[i]))-math.log(SUP)-float(lq[i])
    assert np.array_equal(np.isfinite(logw),np.isfinite(lwsrc))
    delta=float(np.max(abs(logw[np.isfinite(logw)]-lwsrc[np.isfinite(lwsrc)])))
    assert delta<1e-9,('F91V2_RECOMPUTED_NATIVE_WEIGHT_MISMATCH',seed,delta)
    norm=logsumexp(logw);wt=np.exp(logw-norm)
    ess=1/float(np.dot(wt,wt));maxW=float(wt.max());logI=float(norm-math.log(512))
    halfI=float(logsumexp(logw[:256])-math.log(256))
    phases=[]
    for mask in (z[:,2]<=0,z[:,2]>0):
       a=wt[mask];phases.append(float(a.sum()**2/np.dot(a,a)) if np.dot(a,a)>0 else 0.)
    metric=sr['diagnostics']
    assert abs(metric['ESS']-ess)<1e-7
    assert abs(metric['max_weight_fraction']-maxW)<1e-9
    assert abs(metric['log_conditional_integral']-logI)<1e-8
    assert all(abs(m['ESS']-x)<1e-7 for m,x in zip(metric['phase_partitions'],phases))
    assert abs(sr['prefixes'][1]['log_conditional_integral']-halfI)<1e-8
    assert sr['original_raw_jsonl_sha256']==sha(raw)
    assert sr['source_npz_sha256']==sha(npz)
    truecalls=sum(e['reason'] in ('FINITE','RATE_FLOOR') for e in events)
    assert truecalls==sr['new_photon_calls']
    report['seed_results'].append({'seed':seed,'draws':512,'ESS':ess,'max_weight_fraction':maxW,'logI':logI,
        'drift_256_to_512':abs(halfI-logI),'phase_half_ESS':phases,'max_reconstructed_abs_logweight_error':delta,
        'new_native_photon_calls_preserved':truecalls,
        'npz_sha256':sha(npz),'source_jsonl_sha256':sha(raw),'summary_sha256':sha(summ),
        'independently_passed_per_seed':ess>=100 and maxW<=.05 and min(phases)>=30 and abs(halfI-logI)<=.1})
if len(report['seed_results'])==4 and not report['partial_seeds']:
    vals=report['seed_results'];spread=max(x['logI'] for x in vals)-min(x['logI'] for x in vals)
    report['observed_logI_spread']=spread
    report['accepted']=all(x['independently_passed_per_seed'] for x in vals) and spread<=.2
    report['status']='FOUR_FRESH_NATIVE_SEEDS_VERIFIED_PASS' if report['accepted'] else 'FOUR_FRESH_NATIVE_SEEDS_VERIFIED_FAIL'
else:report['status']='IN_PROGRESS_PARTIAL_RAW_CHECK_NO_FULL_ACCEPTANCE_CLAIM'
OUT.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf8')
print(json.dumps({'status':report['status'],'complete_count':len(report['seed_results']),
 'partial':report['partial_seeds'],'pending':report['pending_seeds'],
 'seeds':[{'seed':x['seed'],'ESS':x['ESS'],'maxW':x['max_weight_fraction'],'pass':x['independently_passed_per_seed']} for x in report['seed_results']],
 'report_sha256':sha(OUT)},ensure_ascii=False),flush=True)

