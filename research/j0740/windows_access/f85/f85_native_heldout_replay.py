#!/usr/bin/env python3
"""F85: source-pinned actual X-PSI heldout seed 198301 diagnostics; never certifies new photons.

Summary-only mode computes exact finite-weight identities from the pre-existing
2048-row independently audited *summary*. Raw replay, when the actual Windows
NPZ/JSONL are accessible, re-derives the complete sample weights without any
new X-PSI call.  All counterfactual alterations are diagnostic, NOT estimates.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

SEED = 198301
DRAWS = 2048
GATE_ESS = 400.0
GATE_MAXW = 0.02
GATE_PHASE_ESS = 100.0
GATE_HALF_DRIFT = 0.10
# Git blob SHA's of source audits in GitHub before this study, not SHA256 hashes.
ORIGINAL_SUMMARY_BLOB = '3c53b253c509c401faf60a85ae22e49bdeb91074'
ORIGINAL_TRAINING_BLOB = '0f6e1662b336b31eb9f5d0101756beb83028e2d5'
ORIGINAL_SUMMARY = Path(__file__).resolve().parents[1] / 'v3_frozen_training_audit_20261114' / 'v3_first_heldout_198301_FAIL_verified.json'
ORIGINAL_TRAINING = Path(__file__).resolve().parents[1] / 'v3_frozen_training_audit_20261114' / 'v3_training_frozen_density_audit.json'

class SourceError(ValueError):
    pass


def git_blob_sha(content: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()


def read_source_json(path: Path, expected_git_blob_sha: str):
    bs = Path(path).read_bytes()
    digest = git_blob_sha(bs)
    if digest != expected_git_blob_sha:
        raise SourceError(f'F85_ORIGINAL_GITHUB_AUDIT_BYTE_DRIFT: {path}: {digest}')
    return json.loads(bs)


def finite(v: object, key: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v):
        raise SourceError(f'F85_BAD_NUMERIC_{key}')
    return float(v)


def audit(seed_report: dict, training_report: dict) -> dict:
    """Compute exact algebra from real *historical summary*, never fake new photons."""
    if seed_report.get('seed') != SEED or seed_report.get('sample_identity_rows_pass') != DRAWS:
        raise SourceError('F85_WRONG_SEED_OR_DRAW_COUNT')
    if seed_report.get('status') != 'FAIL' or seed_report.get('kind') != 'EXACT_2048_DRAW_HELDOUT_FIRST_SEED_FAIL':
        raise SourceError('F85_EXPECTED_FAILED_REAL_HELDOUT_NOT_FOUND')
    if seed_report['frozen_proposal_sha256'] != training_report['frozen_proposal_sha256']:
        raise SourceError('F85_TRAINING_HELDOUT_PROPOSAL_MISMATCH')
    if not training_report.get('frozen_before_validation'):
        raise SourceError('F85_PROPOSAL_WAS_NOT_FROZEN')
    if seed_report.get('max_abs_logweight_reconstruction_difference') != 0:
        raise SourceError('F85_ACTUAL_WEIGHT_RECONSTRUCTION_NOT_EXACT')
    s = seed_report['independently_reconstructed']
    ess = finite(s['ESS'], 'ESS')
    w = finite(s['max_weight_fraction'], 'max_weight_fraction')
    drift = finite(s['half_full_logI_drift'], 'half_full_logI_drift')
    phase_ess = finite(s['min_phase_half_ESS'], 'min_phase_half_ESS')
    tops = seed_report['top_samples']
    if not tops or any(finite(x['fraction_of_total_normalized_weight'], 'top') <= 0 for x in tops):
        raise SourceError('F85_BAD_TOP_SAMPLES')
    if [x['index'] for x in tops] != sorted((x['index'] for x in tops),key=lambda k:-next(y['fraction_of_total_normalized_weight'] for y in tops if y['index']==k)):
        raise SourceError('F85_TOP_LIST_ORDER_CHANGED')
    if len({x['index'] for x in tops}) != len(tops):
        raise SourceError('F85_DUPLICATE_TOP_INDEX')
    first = tops[0]
    if first['index'] != 932 or not math.isclose(w,first['fraction_of_total_normalized_weight'],abs_tol=1e-14,rel_tol=0):
        raise SourceError('F85_TOP_REAL_WITNESS_CHANGED')
    density_ratio = finite(first['q_v3_over_q_base'], 'qratio')
    if not 0 < density_ratio < 1:
        raise SourceError('F85_TOP_IS_NOT_V3_UNDER_DENSE')
    shares = first['mixture_pdf_component_share']
    if abs(sum(shares.values())-1)>5e-12:
        raise SourceError('F85_MIXTURE_SHARES_NOT_NORMALIZED')
    recorded_gates={'ESS_min_400':ess>=GATE_ESS,'maxW_max_0p02':w<=GATE_MAXW,'drift_max_0p10':drift<=GATE_HALF_DRIFT,'min_phase_ESS_min_100':phase_ess>=GATE_PHASE_ESS}
    if seed_report.get('gates') != recorded_gates or recorded_gates['maxW_max_0p02'] or not all(v for k,v in recorded_gates.items() if k!='maxW_max_0p02'):
        raise SourceError('F85_ORIGINAL_FIXED_ACCEPTANCE_GATE_DRIFT')
    # Removing or modifying weights below is an algebraic sensitivity ONLY.
    sum_square_share = w*w*ess
    leftover_square=1/ess-w*w
    if leftover_square<=0:
        raise SourceError('F85_INVALID_EFF_SAMPLE_SIZE')
    leave_one_out_ess=(1-w)**2/leftover_square
    needed_other_weight_mass_ratio=w/GATE_MAXW-1  # additional original-normalized total mass, if top stays fixed
    local_top_q_gain=w*(1-GATE_MAXW)/(GATE_MAXW*(1-w))  # if ONLY numerator of top IS weight changes
    adjusted_base_weight=w*density_ratio/(1-w+w*density_ratio)
    return {
        'schema':'J0740_F85_REAL_NATIVE_V3_FAILED_SEED_CONCENTRATION_AUDIT_V1',
        'source':'already-verified exact 2048-sample real X-PSI holdout summary, NOT new likelihood',
        'historical_seed':SEED,'historical_draws':DRAWS,
        'original_source_sha256':seed_report['source_model_sha256'],
        'original_frozen_proposal_sha256':seed_report['frozen_proposal_sha256'],
        'original_npz_sha256':seed_report['npz_sha256'],
        'original_jsonl_sha256':seed_report['jsonl_sha256'],
        'historical_gates_passed_except_maxW':recorded_gates,
        'actual_top_index':first['index'],
        'real_ESS':ess, 'real_max_normalized_weight':w,
        'true_max_weight_gate':GATE_MAXW,
        'maxW_to_gate_ratio':w/GATE_MAXW,
        'top_weight_squared_fraction_of_all_weight_squares':sum_square_share,
        'real_top_proposal_density_q_v3_over_q_base':density_ratio,
        'real_top_mixture_density_component_shares':shares,
        'real_top_latent_phase_2':first['z2'], 'real_top_latent_phase_6':first['z6'],
        'real_second_highest_weight':tops[1]['fraction_of_total_normalized_weight'],
        'top10_real_normalized_mass':sum(x['fraction_of_total_normalized_weight'] for x in tops),
        'actual_sample_count_of_finite_photon_calls':s['finite_source_likelihood_count'],
        'actual_half_full_logI_drift':drift,
        'counterfactual_DO_NOT_USE_FOR_SCIENCE':{
            'hypothetical_ESS_if_top_sample_removed':leave_one_out_ess,
            'hypothetical_top_weight_if_only_top_q_used_qbase':adjusted_base_weight,
            'top_local_q_factor_needed_if_others_fixed':local_top_q_gain,
            'other_weights_total_mass_increase_needed_if_top_fixed':needed_other_weight_mass_ratio,
            'counterfactuals_do_not_change_original_weights_or_change_FAIL_to_PASS':True,
        },
        'real_seed_198301_status':'FAIL_UNCHANGED',
        'new_native_XPSI_photon_calls_this_audit':0,
        'raw_2048_row_NPZ_JSONL_replayed_this_run':False,
        'full_MR_nuisance_convergence':'NOT_ESTABLISHED',
        'physical_seven_EOS_Bayes':'NOT_RUN',
        'necessary_next_experiment':'new preregistered independent native likelihood draws, no reuse of 198301 for acceptance after candidate adaptation; fixed original gate ESS>=400 maxW<=0.02',
    }


def raw_replay(npz: Path, jsonl: Path, seed_report: dict) -> dict:
    """Optional original *private* full-sample replay, fails closed if missing.

    Only reads existing bytes; NEVER calls native X-PSI or modifies source.
    """
    if not npz.is_file() or not jsonl.is_file():
        raise FileNotFoundError("F85_ORIGINAL_PRIVATE_RAW_NPZ_AND_JSONL_UNAVAILABLE")
    import numpy as np
    from scipy.special import logsumexp
    if hashlib.sha256(npz.read_bytes()).hexdigest()!=seed_report['npz_sha256'] or hashlib.sha256(jsonl.read_bytes()).hexdigest()!=seed_report['jsonl_sha256']:
        raise SourceError('F85_ORIGINAL_REAL_NPZ_JSONL_SHA_MISMATCH')
    with np.load(npz,allow_pickle=False) as d:
        if set(['z','logweights'])-set(d.files):
            raise SourceError('F85_UNKNOWN_ORIGINAL_NPZ_SCHEMA')
        z=np.asarray(d['z'],dtype=float); logw=np.asarray(d['logweights'],dtype=float)
    if z.shape!=(DRAWS,13) or logw.shape!=(DRAWS,):
        raise SourceError('F85_WRONG_ORIGINAL_REAL_ARRAY_SHAPE')
    if not np.isfinite(z).all() or not np.isfinite(logw).any() or np.isnan(logw).any():
        raise SourceError('F85_NONFINITE_Z_OR_NAN_LOGWEIGHT')
    rows=[json.loads(l) for l in jsonl.read_text(encoding='utf-8').splitlines() if l.strip()]
    if len(rows)!=DRAWS or [r['index'] for r in rows]!=list(range(DRAWS)):
        raise SourceError('F85_REAL_EVENT_ROWS_NOT_IDENTICAL')
    if any(not np.array_equal(np.asarray(r['z'],dtype=float),z[i]) for i,r in enumerate(rows)):
        raise SourceError('F85_REAL_EVENT_Z_NOT_IDENTICAL')
    vals=[]
    for i,r in enumerate(rows):
        logL=r.get('logL')
        if logL is None:
            vals.append(-np.inf)
            continue
        if 'logq' not in r:
            raise SourceError('F85_REAL_EVENT_LOGQ_MISSING')
        native_base=-0.5*(13*math.log(2*math.pi)+float(np.dot(z[i],z[i])))
        vals.append(float(logL)+native_base-float(r['logq']))
    if not np.allclose(np.asarray(vals),logw,atol=1e-9,rtol=0):
        raise SourceError('F85_REAL_LOGWEIGHT_NOT_RECONSTRUCTIBLE')
    weights=np.exp(logw-logsumexp(logw))
    ess=1/float(np.dot(weights,weights)); m=float(max(weights)); top=int(np.argmax(weights))
    obs=seed_report['independently_reconstructed']
    if not math.isclose(ess,obs['ESS'],abs_tol=5e-8) or not math.isclose(m,obs['max_weight_fraction'],abs_tol=1e-10) or top!=seed_report['top_samples'][0]['index']:
        raise SourceError('F85_REAL_REPLAY_DOES_NOT_MATCH_OLD_AUDIT')
    return {'status':'BYTE_VERIFIED_REAL_RAW_REPLAY_PASS','ess':ess,'max_weight':m,'top_index':top,'original_accepted':False,'new_photon_calls':0}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--summary',type=Path,default=ORIGINAL_SUMMARY)
    p.add_argument('--training',type=Path,default=ORIGINAL_TRAINING)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--npz',type=Path)
    p.add_argument('--jsonl',type=Path)
    a=p.parse_args()
    r=read_source_json(a.summary,ORIGINAL_SUMMARY_BLOB)
    t=read_source_json(a.training,ORIGINAL_TRAINING_BLOB)
    result=audit(r,t)
    if (a.npz is None)!=(a.jsonl is None):
        raise SourceError('F85_BOTH_RAW_NPZ_AND_JSONL_REQUIRED')
    if a.npz:
        result['raw_replay']=raw_replay(a.npz,a.jsonl,r)
        result['raw_2048_row_NPZ_JSONL_replayed_this_run']=True
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'status':result['real_seed_198301_status'],'new_photon_calls':0,'maxW':result['real_max_normalized_weight'],'top_q_ratio':result['real_top_proposal_density_q_v3_over_q_base']},sort_keys=True))

if __name__=='__main__':
    main()
