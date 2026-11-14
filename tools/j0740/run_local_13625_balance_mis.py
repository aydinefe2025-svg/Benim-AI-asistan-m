"""No-photon, fail-closed K4/K8 deterministic balance MIS readback for J0740.

Run ONLY after K8 4x512 native run has completed and source matching is checked.
Original D: data are read-only; write a new report to SentinelX workspace only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path

# Avoid resource spikes on the PC and preserve original local source files.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np
from scipy.special import logsumexp, ndtri
from scipy.stats import truncnorm
from balance_mis_audit import EvidenceError, evaluate_pair, summarize_four_pairs

SEEDS = (197501, 197503, 197507, 197511)
TRAINING = (194501, 194503, 194507, 194511)
RADIUS, MASS = 13.625, 2.0
SOURCE_NAMES = [
    "config_postprocess_J0740_gamma.ini", "CustomInstrument.py",
    "CustomSignal.py", "CustomInterstellar.py", "CustomPhotosphere.py",
    "CustomPrior_GLS_compressed_scaling_Dfix.py", "main_lp40k_Xse001_Dfix.py",
]


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while part := f.read(1024*1024):
            h.update(part)
    return h.hexdigest()


def _check_manifest(m, *, name, source_sha):
    if m.get('status') != 'TAILCORR_HELDOUT_COMPLETE':
        raise EvidenceError(f'{name}: native job not complete')
    if m.get('model_sha256') != source_sha or m.get('source_prior_likelihood_changed') is not False:
        raise EvidenceError(f'{name}: source model hash or source prior/likelihood changed')
    if m.get('EOS_Bayes') != 'NOT_RUN' or m.get('xpsi_version') != '1.2.0':
        raise EvidenceError(f'{name}: unexpected EOS or X-PSI version')
    if m.get('training_point') != [MASS, 14.0] or m.get('training_seeds') != list(TRAINING):
        raise EvidenceError(f'{name}: unexpected training data')
    if m.get('budget_per_seed') != 512:
        raise EvidenceError(f'{name}: expected 512 photon draws/seed')
    a = m.get('heldout_points')
    if len(a) != 1 or a[0]['mass_radius'] != [MASS,RADIUS] or a[0]['seeds'] != list(SEEDS):
        raise EvidenceError(f'{name}: held-out point/seeds mismatch')
    if m.get('passed_all_points') is not False or a[0]['status'] != 'FAIL':
        raise EvidenceError(f'{name}: original FAIL record is unexpected/missing')
    if [x['seed'] for x in m.get('runs',[])] != list(SEEDS):
        raise EvidenceError(f'{name}: four original per-seed runs missing')
    return m['support_normalization']


def _saved_data(folder, seed, model_sha):
    stem = f'M2.000_R13.62_seed{seed}'
    npz_path = folder / f'{stem}_512_local.npz'
    jsonl_path = folder / f'{stem}_evals.jsonl'
    with np.load(npz_path, allow_pickle=False) as a:
        z, lw = a['z'].copy(), a['logweights'].copy()
    ev = [json.loads(line) for line in jsonl_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if z.shape != (512,13) or lw.shape != (512,) or len(ev) != 512:
        raise EvidenceError(f'{folder.name}/{seed}: wrong NPZ or JSONL dimensions')
    if not np.all(np.isfinite(z)) or not np.all(np.isfinite(lw) | np.isneginf(lw)):
        raise EvidenceError(f'{folder.name}/{seed}: invalid coordinates or weights')
    if any(e.get('index') != i or e.get('model_sha256') != model_sha or
           e.get('mass_radius') != [MASS,RADIUS] for i,e in enumerate(ev)):
        raise EvidenceError(f'{folder.name}/{seed}: event/model/target mismatch')
    if not np.array_equal(np.asarray([e['z'] for e in ev],dtype=float), z):
        raise EvidenceError(f'{folder.name}/{seed}: JSONL x NPZ samples differ')
    return z,lw,ev,{'npz_sha256':_sha(npz_path),'jsonl_sha256':_sha(jsonl_path)}


def _validate_weights(z,lw,events,logq,acceptance):
    normal = -0.5*np.einsum('ij,ij->i', z,z)-6.5*math.log(2*math.pi)
    ll = np.asarray([-np.inf if e.get('logL') is None else float(e['logL']) for e in events])
    if np.isnan(ll).any() or np.isposinf(ll).any():
        raise EvidenceError('invalid JSONL photon logL')
    recalculated = ll + normal - math.log(acceptance) - logq
    finite=np.isfinite(lw)
    if not np.array_equal(finite,np.isfinite(recalculated)):
        raise EvidenceError('source/weight finite-support mask differs')
    error=float(np.max(np.abs(recalculated[finite]-lw[finite]))) if finite.any() else 0.0
    if error>1e-8:
        raise EvidenceError(f'original weight reconstruction failure: {error}')
    return error


def calculate(root, native, photon, report_to):
    work = root/'work'
    exp = work/'MR_tailcorr_paired_K4K8_20261112'/'heldout_R13_625'
    model = work/'MR14_50_training_K2'/'real-model'
    source_sha = hashlib.sha256(''.join(_sha(model/n) for n in SOURCE_NAMES).encode()).hexdigest()
    k4m=json.loads((exp/'K4/run_manifest.json').read_text(encoding='utf-8'))
    k8m=json.loads((exp/'K8/run_manifest.json').read_text(encoding='utf-8'))
    normalization=_check_manifest(k4m,name='K4',source_sha=source_sha)
    if _check_manifest(k8m,name='K8',source_sha=source_sha)!=normalization:
        raise EvidenceError('K4 K8 source normalization mismatches')
    if not isinstance(normalization,(float,int)) or not math.isfinite(normalization) or normalization<=0:
        raise EvidenceError('invalid source acceptance normalization')
    sys.path[:0]=[str(native),str(model),str(work)]
    from temperature_coupling import Coupling,TransportProposal
    from conditional_proposal import condition
    from normalized_source_prior import RLO,RHI
    from torus_conditional_proposal import TorusConditionalProposal
    flowpath = photon/'temperature_transport_K48_local.npz'
    with np.load(flowpath,allow_pickle=False) as f:
        flow=Coupling(f['coupling_shift'],f['coupling_scale'],f['coupling_coef'])
        floww, flowmean, flowcov=[f[n].copy() for n in ('weights','means','covs')]

    def base_at(m,r):
        fixed=ndtri([truncnorm.cdf(m,-5,5,loc=2.082,scale=.0703),(r-RLO)/(RHI-RLO)])
        w,means,covs=condition(floww,flowmean,flowcov,fixed)
        return TransportProposal(w,means,covs,flow,fixed=fixed)

    trdir=work/'MR_tailcorr_v1_holdout_20261111_v4'
    ta=[]
    for seed in TRAINING:
        with np.load(trdir/f'M2.000_R14.00_seed{seed}_512_local.npz',allow_pickle=False) as f:
            ta.append((f['z'].copy(), f['logweights'].copy()))
    ztr=np.vstack([a for a,b in ta]); wtr=np.concatenate([b for a,b in ta])
    base_tr=base_at(MASS,14.0)
    k4=TorusConditionalProposal.fit(ztr,wtr,base_tr,components=4)
    k8=TorusConditionalProposal.fit(ztr,wtr,base_tr,components=8)
    target=base_at(MASS,RADIUS)
    def density(k,z):
        k.base=target
        tail=TorusConditionalProposal(k.weights.copy(),k.means.copy(),k.covs*4.,
          k.phase_means.copy(),np.maximum(k.phase_kappas/4.,.05),target)
        return logsumexp(np.vstack((math.log(.5)+target.logpdf(z),
                  math.log(.25)+k.adapted_logpdf(z),
                  math.log(.25)+tail.adapted_logpdf(z))),axis=0)

    results=[];digests=[]
    for seed in SEEDS:
        za,lwa,ea,da=_saved_data(exp/'K4',seed,source_sha)
        zb,lwb,eb,db=_saved_data(exp/'K8',seed,source_sha)
        aa,ab=density(k4,za),density(k8,za)
        ba,bb=density(k4,zb),density(k8,zb)
        errA=_validate_weights(za,lwa,ea,aa,normalization)
        errB=_validate_weights(zb,lwb,eb,bb,normalization)
        result=evaluate_pair(seed=seed,za=za,lwa=lwa,logqa_on_a=aa,logqb_on_a=ab,
                zb=zb,lwb=lwb,logqa_on_b=ba,logqb_on_b=bb,phase_axis=2)
        result['source_weight_reconstruction_max_error']=max(errA,errB)
        results.append(result)
        digests.append({'seed':seed,'K4':da,'K8':db})
    complete=summarize_four_pairs(results)
    complete.update({'source_model_sha256':source_sha,
        'flow_training_npz_sha256':_sha(flowpath),
        'input_evidence_files':digests,
        'original_K4_status':k4m['heldout_points'][0]['status'],
        'original_K8_status':k8m['heldout_points'][0]['status'],
        'source_normalization':normalization,
        'source_transform_or_XPSI_likelihood_reexecuted':False,
        'all_original_K4_K8_outputs_untouched':True})
    report_to.parent.mkdir(parents=True,exist_ok=True)
    if report_to.exists():
        raise EvidenceError('output report already exists; refuse overwrite')
    report_to.write_text(json.dumps(complete,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return complete


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(r'D:\PSR_J0740+6620'))
    p.add_argument('--native',type=Path,default=Path(r'C:\Users\User\Documents\Codex\2026-11-08\codex-psr-j0740-6620-ara-tirmasina\native_prior'))
    p.add_argument('--photon',type=Path,default=Path(r'C:\Users\User\Documents\Codex\2026-11-08\codex-psr-j0740-6620-ara-tirmasina\evidence\native_photon'))
    p.add_argument('--report-to',type=Path,default=Path(r'C:\Users\User\AppData\Local\SentinelX\workspace\j0740_13625_balance_mis_report.json'))
    a=p.parse_args()
    try:
        result=calculate(a.root,a.native,a.photon,a.report_to)
    except (OSError,KeyError,ValueError,AssertionError) as exc:
        print('FAIL_CLOSED:',exc,file=sys.stderr)
        return 2
    print(json.dumps({'status':result['status'], 'gates':result['gates'],
           'per_seed':[{'seed':p['seed'],'ESS':p['ESS'],'maxW':p['max_weight_fraction'],
                'phaseESS':p['min_phase_ESS'],'drift':p['half_to_full_logI_drift'],
                'status':p['pair_status']} for p in result['pair_results']],
           'output':str(a.report_to)},allow_nan=False))
    return 0

if __name__=='__main__':raise SystemExit(main())