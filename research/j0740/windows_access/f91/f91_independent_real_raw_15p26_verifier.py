#!/usr/bin/env python3
"""F91 independent replay of the real ongoing M2.073 R15.26 conditional-tail X-PSI 512x4 seeds.
NEVER evaluates photon likelihood; never edits source or real heldout draws.
"""
from pathlib import Path
import hashlib, json, math, sys
import numpy as np
from scipy.special import logsumexp, ndtri
from scipy.stats import truncnorm, qmc
ROOT=Path(r'C:\Users\User\Documents\Codex\2026-11-08\codex-psr-j0740-6620-ara-tirmasina')
NATIVE=ROOT/'native_prior'
sys.path.insert(0,str(NATIVE))
from temperature_coupling import Coupling, TransportProposal
from conditional_proposal import condition
from conditional_tail_patch import ConditionalTailPatchedProposal
from normalized_source_prior import RLO,RHI
from support_normalization import nuisance_acceptance
REC=ROOT/'records'/'A01.01.51'/'PSR_J0740+6620'
EV=ROOT/'evidence'/'native_photon'
DESIGN=REC/'J0740_15p26_CONDITIONAL_TAIL_PATCH_DESIGN_20261121.json'
TARGET=Path(r'C:\Users\User\AppData\Local\SentinelX\workspace\F91_15p26_independent_native_raw_replay.json')
EXPECTED_DESIGN_SHA='50477db36217448177ef489980b395d6a92f37ec2409f2187b3420a0267bff82'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def close(a,b,eps=2e-8):
    if not (math.isfinite(a) and math.isfinite(b) and abs(a-b)<eps):
        raise ValueError(f'INDEPENDENT_REPLAY_DIFFERENCE_{a}_{b}')
assert sha(DESIGN)==EXPECTED_DESIGN_SHA,'F91_DESIGN_UNEXPECTED_SOURCE_OR_MUTATED'
d=json.loads(DESIGN.read_text(encoding='utf8'))
assert d['fresh_validation_seeds']==[211301,211303,211307,211311]
assert d['epsilon']==.1 and d['df']==8.0
assert d['fresh_validation_started'] is False
model=EV/'temperature_transport_K48_local.npz'
assert sha(model)==d['base_model_sha256'],'F91_FLOW_SHA_MISMATCH'
with np.load(model,allow_pickle=False) as f:
    flow=Coupling(f['coupling_shift'],f['coupling_scale'],f['coupling_coef'])
    zz=ndtri([truncnorm.cdf(2.073,-5,5,loc=2.082,scale=.0703),(15.26-RLO)/(RHI-RLO)])
    w,means,covs=condition(f['weights'],f['means'],f['covs'],zz)
base=TransportProposal(w,means,covs,flow,fixed=zz)
proposal=ConditionalTailPatchedProposal(base,flow,zz,
    np.asarray([x['center_w_nuisance'] for x in d['tail_centers']]),
    np.asarray(d['selected_covariances']),d['epsilon'],d['df'])
support=nuisance_acceptance()
assert abs(support-.24947354926879406)<1e-13
LN13=-6.5*math.log(2*math.pi)
r={'schema':'J0740_F91_SOURCE_LOCKED_INDEPENDENT_REAL_NATIVE_15p26_REPLAY_V1',
   'frozen_design_sha256':EXPECTED_DESIGN_SHA,
   'source_flow_sha256':sha(model),
   'original_source_model_SHA256':d['frozen_model_sha256'],
   'point':[2.073,15.26],
   'original_acceptance_thresholds':{'ess_min':100,'maxW_max':.05,'phase_ess_min':30,'logI_range_max':.2,'half_256_to_512_logI_drift_max':.1},
   'frozen_seed_order':d['fresh_validation_seeds'],
   'num_new_photon_calls_in_this_independent_replay':0,
   'seeds':[],'pending_seeds':[],
   'claim_eos_full_bayes':'NOT_RUN',
   'method':'512 Sobol proposal samples per seed and raw source-native JSONL reconstructed with exact q and support prior, without XPSI calls'}
for seed in d['fresh_validation_seeds']:
    NPZ=EV/f'MR_anchor_2_tailpatch_seed_{seed}_512_local.npz'
    raw=EV/f'MR_anchor_2_tailpatch_seed_{seed}_evals_local.jsonl'
    src=EV/f'MR_anchor_2_tailpatch_seed_{seed}_512_local.json'
    if not all(p.is_file() for p in (NPZ,raw,src)):
        r['pending_seeds'].append(seed);continue
    with np.load(NPZ,allow_pickle=False) as f:
        z=np.asarray(f['z'],dtype=float);lw=np.asarray(f['logweights'],dtype=float)
    assert z.shape==(512,13) and lw.shape==(512,) and np.isfinite(z).all()
    zz=proposal.from_unit(qmc.Sobol(17,scramble=True,seed=int(seed)).random_base2(9))
    maxz=float(np.max(np.abs(zz-z)))
    assert maxz<1e-12,('F91_ORIGINAL_512_QMC_DRAW_IDENTITY_FAIL',seed,maxz)
    evs=[json.loads(line) for line in raw.read_text(encoding='utf8').splitlines() if line.strip()]
    assert len(evs)==512,('F91_INCOMPLETE_JSONL',seed,len(evs))
    logq=proposal.logpdf(z)
    recomputed=np.full(512,-np.inf)
    for i,event in enumerate(evs):
        assert event['index']==i and event['seed']==seed
        assert event['tail_proposal_sha256']==EXPECTED_DESIGN_SHA
        assert event['model_sha256']==d['frozen_model_sha256']
        assert event['fixed_mass_radius']==[2.073,15.26]
        assert np.max(np.abs(np.asarray(event['z'],float)-z[i]))<1e-12
        ll=event['logL']
        if ll is not None:
            assert math.isfinite(ll)
            recomputed[i]=ll+LN13-.5*float(np.dot(z[i],z[i]))-math.log(support)-float(logq[i])
    assert np.array_equal(np.isfinite(recomputed),np.isfinite(lw))
    err=float(np.max(np.abs(recomputed[np.isfinite(recomputed)]-lw[np.isfinite(lw)])))
    assert err<1e-8,('F91_LOGWEIGHT_BUG',seed,err)
    norm=logsumexp(recomputed)
    weight=np.exp(recomputed-norm)
    ess=1/float(np.dot(weight,weight));maxw=float(weight.max())
    logi=float(norm-math.log(512))
    l256=float(logsumexp(recomputed[:256])-math.log(256))
    phases=[]
    for mask in (z[:,2]<=0,z[:,2]>0):
        v=weight[mask]
        phases.append(float(v.sum()**2/np.dot(v,v)) if np.dot(v,v)>0 else 0.)
    src_record=json.loads(src.read_text(encoding='utf8'))
    assert src_record['seed']==seed and src_record['draws']==512
    a=src_record['diagnostics']
    close(ess,a['ESS'],2e-7);close(maxw,a['max_weight_fraction'],1e-10)
    close(logi,a['log_conditional_integral'],2e-8)
    for pv,saved in zip(phases,a['phase_partitions']):close(pv,saved['ESS'],2e-7)
    close(abs(l256-logi),abs(src_record['prefixes'][1]['log_conditional_integral']-logi),2e-8)
    r['seeds'].append({'seed':seed,'npz_sha256':sha(NPZ),'jsonl_sha256':sha(raw),'source_summary_sha256':sha(src),
                      'max_source_QMC_z_abs_diff':maxz,
                      'max_abs_recomputed_weight_diff':err,
                      'ESS':ess,'max_weight':maxw,'logI':logi,'phase_ESS':phases,
                      'drift_256_512':abs(l256-logi),
                      'original_photon_calls':src_record['new_photon_calls'],
                      'per_seed_gate':{'ESS_ge_100':ess>=100,'maxW_le_0p05':maxw<=.05,'phase_ESS_min_ge_30':min(phases)>=30,'drift_le_0p1':abs(l256-logi)<=.1}})
if len(r['seeds'])==4:
    ss=r['seeds'];spread=max(x['logI'] for x in ss)-min(x['logI'] for x in ss)
    r['between_seed_logI_spread']=spread
    r['accepted_original_thresholds']=all(all(x['per_seed_gate'].values()) for x in ss) and spread<=.2
    r['status']='PASS_INDEPENDENT_SOURCE_REPLAY_OF_NATIVE_CANDIDATE' if r['accepted_original_thresholds'] else 'FAIL_SOURCE_CANDIDATE_NOT_ACCEPTED'
else:r['status']='PARTIAL_SOURCE_REPLAY_INCOMPLETE_DO_NOT_CLAIM_RESULT'
TARGET.write_text(json.dumps(r,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf8')
print(json.dumps({'status':r['status'],'verified_seeds':[{'seed':x['seed'],'ESS':x['ESS'],'maxW':x['max_weight'],'abs_weight_diff':x['max_abs_recomputed_weight_diff']} for x in r['seeds']],
'pending':r['pending_seeds'],'receipt_sha256':sha(TARGET)},ensure_ascii=False),flush=True)

