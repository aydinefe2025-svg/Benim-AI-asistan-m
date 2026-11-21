#!/usr/bin/env python
"""J0740 F90 immutable native X-PSI v3 local replay, using ORIGINAL manifest's global support normalization.
No new likelihood, no synthetic/posthoc weights, no change to NPZ/JSONL and no per-seed PASS fudging.
"""
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser(description='Reconstruct four original raw X-PSI seeds, without running any new photons')
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    ROOT=a.root
    OUT=a.out
    raw_manifest=(ROOT/'run_manifest.json').read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest()!='3c8d25ada8c148c961187ce18a78575c2c178f1160f3c69bb13614172a9baf53':
        raise ValueError('F90_SOURCE_NATIVE_MANIFEST_HASH_MISMATCH')
    M=json.loads(raw_manifest)
    SUP=M['source_support_normalization']
    assert type(SUP) is float and 0<SUP<1 and abs(SUP-0.24947354926879406)<1e-15
    LOGSUP=math.log(SUP)
    LN13=-6.5*math.log(2*math.pi)
    def lse(a):
        finite=a[np.isfinite(a)]
        assert len(finite)>0
        mx=finite.max()
        return float(mx+np.log(np.exp(finite-mx).sum()))
    def getsha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def compare(a,b,key,tol=1e-8):
        if abs(a-b)>tol:raise AssertionError(f'{key}: {a} != {b}')
    res={'schema':'J0740_F90_REAL_NATIVE_XPSI_V3_FOUR_SEED_RAW_IMMUTABLE_REPLAY_V1',
    'method':'raw NPZ logq, raw JSONL logL/z, source run_manifest numeric global nuisance support; no new photon calls',
    'source_manifest_sha256':getsha(ROOT/'run_manifest.json'),
    'original_source_model_sha256':M['source_model_sha256'],
    'original_proposal_sha256':M['proposal_identity_sha256'],
    'original_support_factor':SUP,'log_support_correction':-LOGSUP,
    'fixed_original_thresholds':M['thresholds'],'seeds':[],
    'new_photon_likelihood_calls':0,
    'previous_native_calls':M['new_photon_likelihood_calls'],
    'original_raw_files_not_modified':True,'acceptance_policy':'ALL_FOUR_ORIGINAL_HELDOUT_SEEDS_PASS_REQUIRED',
    'final_full_MR_photon_Bayes':'NOT_RUN'}
    logs=[]
    for record in M['validation_runs']:
        seed=int(record['seed']);dir=ROOT/'validation'
        npz=next(dir.glob(f'*seed{seed}_2048_local.npz'))
        js=next(dir.glob(f'*seed{seed}_evals.jsonl'))
        assert getsha(npz)==record['npz_sha256'],f'NPZ_HASH_{seed}'
        assert getsha(js)==record['jsonl_sha256'],f'JSONL_HASH_{seed}'
        with np.load(npz,allow_pickle=False) as d:
            z=np.asarray(d['z'],dtype=float)
            lw_saved=np.asarray(d['logweights'],dtype=float)
            logq=np.asarray(d['logq'],dtype=float)
            assert int(d['seed'])==seed
            assert str(d['model_sha256'])==M['source_model_sha256']
            assert list(d['target'])==[2.0,13.625]
        assert z.shape==(2048,13) and lw_saved.shape==(2048,) and logq.shape==(2048,)
        assert np.isfinite(z).all() and np.isfinite(logq).all()
        rows=[json.loads(x) for x in js.read_text(encoding='utf8').splitlines() if x.strip()]
        assert len(rows)==2048
        re=np.full(2048,-np.inf,dtype=float)
        for i,ev in enumerate(rows):
            assert ev['index']==i and ev['seed']==seed
            assert ev['model_sha256']==M['source_model_sha256']
            assert list(ev['mass_radius'])==[2.0,13.625]
            assert np.array_equal(np.asarray(ev['z'],dtype=float),z[i])
            ll=ev['logL']
            if ll is None:continue
            assert type(ll) in (float,int) and math.isfinite(ll)
            re[i]=ll+LN13-0.5*float(np.dot(z[i],z[i]))-LOGSUP-logq[i]
        assert np.array_equal(np.isfinite(re),np.isfinite(lw_saved)),f'FINITE_MASK_{seed}'
        delta=float(np.max(np.abs(re[np.isfinite(re)]-lw_saved[np.isfinite(lw_saved)])))
        assert delta<2e-9,('LOG_WEIGHT_MISMATCH',seed,delta)
        logi=lse(re)-math.log(len(re))
        w=np.zeros(len(re))
        w[np.isfinite(re)]=np.exp(re[np.isfinite(re)]-lse(re))
        ess=1/float(np.dot(w,w)); mw=float(w.max())
        first=lse(re[:1024])-math.log(1024)
        halfdrift=abs(first-logi)
        z2=z[:,2]  # inspect source phase-ess diagnostic expected z2, source convention; don't silently assume
        halfscores=[]
        for mask in (z2<0,z2>=0):
            ww=w[mask]
            halfscores.append(float(ww.sum()**2/np.dot(ww,ww)))
        compare(ess,record['ESS'],f'ESS_{seed}',1e-6)
        compare(mw,record['max_weight_fraction'],f'MAXW_{seed}',1e-10)
        compare(logi,record['logI'],f'LOGI_{seed}',3e-8)
        compare(halfdrift,record['half_to_full_logI_drift'],f'HALFDRIFT_{seed}',3e-8)
        # The phase-half source uses z2 label; validate exact or record mismatch without falsely labeling the original calculation.
        ref_phase=record['phase_half_ESS_z2_negative_positive']
        phase_deltas=[abs(x-y) for x,y in zip(halfscores,ref_phase)]
        gate={'ess_ge_400':ess>=400,'max_weight_le_0p02':mw<=.02,
              'half_full_logI_drift_le_0p1':halfdrift<=.1,
              'source_phase_min_ess_ge_100':record['min_phase_half_ESS']>=100}
        assert (all(gate.values())== (record['status']=='PASS')),f'ACCEPTANCE_MISMATCH_{seed}'
        res['seeds'].append({'seed':seed,'npz_sha256':getsha(npz),'jsonl_sha256':getsha(js),
            'draws':2048,'finite_native_likelihoods':int(np.isfinite(re).sum()),
            'max_abs_recomputed_logweight_difference':delta,
            'ESS':ess,'max_weight_fraction':mw,'max_weight_index':int(np.argmax(w)),
            'recomputed_logI':logi,'half_to_full_drift':halfdrift,
            'source_phase_half_ESS':ref_phase,'recomputed_phase_half_ESS_check':halfscores,
            'source_phase_delta_max':max(phase_deltas),
            'gates':gate,'status':'PASS' if all(gate.values()) else 'FAIL'})
        logs.append(re)
    l2=np.concatenate(logs)
    pool_ess=(lambda a:1/float(np.dot(a,a)))(np.exp(l2-lse(l2)))
    pool_maxw=float(np.exp(l2[np.isfinite(l2)].max()-lse(l2)))
    res['pooled_diagnostic_not_per_seed_acceptance']={'ESS':pool_ess,'max_weight':pool_maxw,'logI':lse(l2)-math.log(len(l2)),
     'scientific_limit':'Pooling four fixed-proposal independent seeds is a separate combined diagnostic, DOES NOT reverse 198301 original per-seed failure.'}
    res['source_198301_FAIL_unmodified']=res['seeds'][0]['status']=='FAIL'
    assert res['source_198301_FAIL_unmodified']
    res['overall_fixed_original_four_seed_acceptance']='PASS' if all(x['status']=='PASS' for x in res['seeds']) else 'FAIL_UNCHANGED'
    OUT.write_text(json.dumps(res,ensure_ascii=False,indent=2,allow_nan=False,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(OUT),'sha256':getsha(OUT),
    'status':res['overall_fixed_original_four_seed_acceptance'],
    'per_seed':[{'seed':q['seed'],'status':q['status'],'ESS':q['ESS'],'maxW':q['max_weight_fraction'],'max_weight_error':q['max_abs_recomputed_logweight_difference'],'phase_delta':q['source_phase_delta_max']} for q in res['seeds']],
    'pooled':res['pooled_diagnostic_not_per_seed_acceptance']},ensure_ascii=False))

if __name__=='__main__':
    main()
