#!/usr/bin/env python3
"""J0740 F91 v2: source-pinned defensive-tail independent photon-native heldout.
Four NEW seeds preregistered before their photon likelihoods were called.
Old 21130x validation is development only and its FAIL is NEVER overwritten.
No photon data, 13D nuisance samples, or source model files are uploaded to public GitHub.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, os, sys, time
from pathlib import Path
ROOT=Path(r'C:\Users\User\Documents\Codex\2026-11-08\codex-psr-j0740-6620-ara-tirmasina')
NATIVE=ROOT/'native_prior'
REC=ROOT/'records'/'A01.01.51'/'PSR_J0740+6620'
EV=ROOT/'evidence'/'native_photon'
BASE=Path(r'C:\Users\User\AppData\Local\SentinelX\workspace')
DESIGN=BASE/'J0740_15p26_V2_frozen_after_211307_FAIL_20261121.json'
OUTPUT=BASE/'J0740_F91_V2_fresh_native_validation_20261121'
EXPECTED='82f0393ca7389ae68d1dc5c751d7ff1b24ece790a16a284f22f5155b7ec25a2f'
NATIVE_SOURCE='be896b89f38736dfa41eb296853ba021c6248dd389dacc88f6ecbfaff755c010'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(DESIGN)!=EXPECTED:raise RuntimeError('F91V2_FROZEN_DESIGN_BYTES_CHANGED')
design=json.loads(DESIGN.read_text(encoding='utf8'))
if design['status']!='FROZEN_NEW_PROPOSAL_NOT_YET_FRESHLY_EVALUATED':
    raise RuntimeError('NOT_FROZEN_F91V2')
if design['NEW_INDEPENDENT_VALIDATION_SEEDS']!=[211401,211403,211407,211411]:
    raise RuntimeError('PREREGISTERED_SEED_LIST_DRIFT')
import numpy as np
from scipy.special import ndtri, ndtr, logsumexp
from scipy.stats import truncnorm, qmc
sys.path.insert(0,str(NATIVE))
from temperature_coupling import Coupling,TransportProposal
from conditional_proposal import condition
from conditional_tail_patch import ConditionalTailPatchedProposal
from normalized_source_prior import RLO,RHI
from support_normalization import nuisance_acceptance
from probit_proposal import log_phi
from weight_diagnostics import summarize
fixed_z=ndtri([truncnorm.cdf(2.073,-5,5,loc=2.082,scale=.0703),(15.26-RLO)/(RHI-RLO)])
pmodel=EV/'temperature_transport_K48_local.npz'
if sha(pmodel)!=design['underlying_original_flow_sha256']:
    raise RuntimeError('ORIGINAL_15P26_FLOW_NOT_PINNED')
with np.load(pmodel,allow_pickle=False) as b:
    flow=Coupling(b['coupling_shift'],b['coupling_scale'],b['coupling_coef'])
    weights,means,covs=condition(b['weights'],b['means'],b['covs'],fixed_z)
base=TransportProposal(weights,means,covs,flow,fixed=fixed_z)
proposal=ConditionalTailPatchedProposal(base,flow,fixed_z,
     np.asarray(design['centers_in_unit_jacobian_transport_coordinates']),
     np.asarray(design['covariances']),epsilon=design['epsilon'],df=design['df'])
if len(proposal.kernels)!=8 or proposal.epsilon!=.20 or proposal.df!=8.0:
    raise RuntimeError('WRONG_FROZEN_PATCH')
support=float(nuisance_acceptance())
if not abs(support-.24947354926879406)<1e-13:raise RuntimeError('WRONG_SOURCE_NUISANCE_SUPPORT')
seeds=design['NEW_INDEPENDENT_VALIDATION_SEEDS']
OUT=OUTPUT
OUT.mkdir(parents=True,exist_ok=True)
def saved_report(report):
    t=OUT/'run_manifest_v2.json'
    q=t.with_suffix('.tmp')
    q.write_text(json.dumps(report,indent=2,allow_nan=False,sort_keys=True)+'\n',encoding='utf8')
    q.replace(t)
reportpath=OUT/'run_manifest_v2.json'
if reportpath.exists():
    existing=json.loads(reportpath.read_text(encoding='utf8'))
    if existing['frozen_design_sha256']!=EXPECTED:raise RuntimeError('SAVED_F91V2_MANIFEST_DESIGN_CONFLICT')
    report=existing
else:
    report={'schema':'J0740_F91_V2_FRESH_SOURCE_XPSI_NATIVE_PHOTON_VALIDATION_V1',
        'status':'IN_PROGRESS_NOT_ACCEPTED',
        'target':[2.073,15.26],
        'frozen_design_sha256':EXPECTED,
        'existing_failed_seed_211307_remains_FAIL':True,
        'source_likelihood_model_sha256':NATIVE_SOURCE,
        'new_independent_seeds':seeds,
        'draws_each':512,
        'source_nuisance_support':support,
        'acceptance_thresholds':design['FIXED_PRIOR_ACCEPTANCE_GATES'],
        'no_original_likelihood_or_prior_modifications':True,
        'new_native_photon_likelihood_calls':0,
        'runs':[], 'current_seed':None, 'completed_draws_current':0,
        'EOS_Bayes':'NOT_RUN','full_MR_coverage':'NOT_DONE'}
    saved_report(report)
print('F91V2_PROPOSAL_PREFLIGHT',json.dumps({'design_sha256':EXPECTED,'seeds':seeds,
       'grid':design['original_XPSI_15p26_target_mass_radius'],'epsilon':proposal.epsilon,
       'source_support':support,'all_new_seed_file_count':len(list(OUT.glob('*evals.jsonl')))}),flush=True)
for seed in seeds:
    unit=qmc.Sobol(17,scramble=True,seed=int(seed)).random_base2(9)
    if not (np.all(unit>0) and np.all(unit<1)):raise RuntimeError('SOBOL_NOT_IN_OPEN_UNIT_CUBE')
    z=proposal.from_unit(unit)
    q=proposal.logpdf(z)
    if z.shape!=(512,13) or q.shape!=(512,) or not (np.isfinite(z).all() and np.isfinite(q).all()):
       raise RuntimeError('F91V2_INVALID_NONFINITE_PROPOSAL')
if '--preflight-only' in sys.argv:
    print('F91V2_DESIGN_AND_FRESH_4_SOBOL_PROPOSALS_VALID_NO_PHOTON_CALLS',flush=True)
    sys.exit(0)
# Heavy X-PSI initialization only after exact pinned proposal/prereg check.
for dep in ('six_unpacked','wrapt_unpacked'):
    sys.path.insert(0,str(NATIVE/'runtime-deps'/dep))
os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['XPSI_DISABLE_POSTPROCESSING']='1'
import full_bootstrap as boot
xpsi=boot.xpsi
if xpsi.__version__!='1.2.0':raise RuntimeError('XPSI_VERSION_DRIFT')
saved_check=xpsi.Likelihood.check
# Bypass only the reference smoke check already previously executed; do not touch likelihood/equations.
xpsi.Likelihood.check=lambda *args,**kwargs:None
model=NATIVE/'real-model'
model_files=[model/x for x in ('config_postprocess_J0740_gamma.ini','CustomInstrument.py',
    'CustomSignal.py','CustomInterstellar.py','CustomPhotosphere.py',
    'CustomPrior_GLS_compressed_scaling_Dfix.py','main_lp40k_Xse001_Dfix.py')]
digest=hashlib.sha256(''.join(sha(x) for x in model_files).encode()).hexdigest()
if digest!=NATIVE_SOURCE:raise RuntimeError('PINNED_NATIVE_PHOTON_MODEL_DRIFT')
sys.path.insert(0,str(model))
cwd=Path.cwd();os.chdir(model);sys.argv=['J0740_F91V2_NEW_HELDOUT','@'+str(model/'config_postprocess_J0740_gamma.ini')]
spec=importlib.util.spec_from_file_location('J0740_F91V2_real_XPSI_photon',model/'main_lp40k_Xse001_Dfix.py')
mod=importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
finally:
    xpsi.Likelihood.check=saved_check
    os.chdir(cwd)
like=mod.likelihood
print('F91V2_PINNED_REAL_XPSI_LOADED',json.dumps({'source_code_sha256':digest,'XPSI_version':xpsi.__version__}),flush=True)
for seed in seeds:
    if any(row['seed']==seed for row in report['runs']):continue
    started=time.monotonic()
    unit=qmc.Sobol(17,scramble=True,seed=int(seed)).random_base2(9)
    z=proposal.from_unit(unit);lq=proposal.logpdf(z)
    filename=OUT/f'MR15p26_F91V2_seed_{seed}_evals.jsonl'
    saved={}
    if filename.is_file():
        for line in filename.read_text(encoding='utf8').splitlines():
            if line.strip():
                entry=json.loads(line)
                i=entry['index']
                if i in saved or not (0<=i<512):raise RuntimeError('DUPLICATE_OR_BAD_RESUME_INDEX')
                if entry['seed']!=seed or entry['design_sha256']!=EXPECTED or entry['source_model_sha256']!=NATIVE_SOURCE:
                    raise RuntimeError('F91V2_RESUME_METADATA_DRIFT')
                if not np.array_equal(np.asarray(entry['z'],dtype=float),z[i]):
                    raise RuntimeError('F91V2_RESUME_SOBOL_CHANGED')
                saved[i]=entry
        if list(saved)!=list(range(len(saved))):raise RuntimeError('F91V2_RESUME_NONPREFIX_GAP')
    logs=[];newcalls=0;reasons=[]
    for i,zi in enumerate(z):
        if i in saved:
            e=saved[i]
        else:
            u=ndtr(zi)
            pars=like.prior.inverse_sample(np.r_[ndtr(fixed_z),u])
            reason='SOURCE_SUPPORT';ll=None
            if np.isfinite(like.prior()):
                newcalls+=1;value=float(like(pars,reinitialise=True,force=True))
                if not math.isfinite(value):raise RuntimeError('F91V2_NONFINITE_NATIVE_C_RESULT')
                if value>-1e80:ll=value;reason='FINITE'
                else:reason='RATE_FLOOR'
            e={'index':i,'seed':seed,'z':zi.tolist(),'logL':ll,'reason':reason,
                 'design_sha256':EXPECTED,'source_model_sha256':NATIVE_SOURCE,'fixed_mass_radius':[2.073,15.26]}
            with filename.open('a',encoding='utf8',newline='\n') as fh:
                fh.write(json.dumps(e,allow_nan=False,separators=(',',':'))+'\n')
                fh.flush()
        logL=-np.inf if e['logL'] is None else e['logL']
        logs.append(logL+float(log_phi(zi))-math.log(support)-float(lq[i]))
        reasons.append(e['reason'])
        if (i+1)%64==0:
            report['current_seed']=seed;report['completed_draws_current']=i+1
            saved_report(report)
            print('F91V2_NATIVE_PROGRESS',json.dumps({'seed':seed,'draws':i+1,'new_native_likelihood_calls_this_seed':newcalls}),flush=True)
    lw=np.asarray(logs)
    if lw.shape!=(512,):raise RuntimeError('BAD_REAL_WEIGHT_COUNT')
    npz=OUT/f'MR15p26_F91V2_seed_{seed}_512_native.npz'
    np.savez_compressed(npz,z=z,logq=lq,logweights=lw,seed=seed)
    prefixes=[{'draws':n,**summarize(lw[:n],z[:n])} for n in (128,256,512)]
    summary={'seed':seed,'draws':512,'new_photon_calls':sum(v in ('FINITE','RATE_FLOOR') for v in reasons),
      'finite_native_likelihood_draws':int(np.isfinite(lw).sum()),
      'diagnostics':prefixes[-1],'prefixes':prefixes,
      'source':{'frozen_design_sha256':EXPECTED,'source_model_sha256':NATIVE_SOURCE,'source_prior_or_likelihood_changed':False},
      'reason_counts':{k:reasons.count(k) for k in sorted(set(reasons))},
      'original_raw_jsonl_sha256':sha(filename),'source_npz_sha256':sha(npz),'elapsed_seconds':time.monotonic()-started}
    rp=OUT/f'MR15p26_F91V2_seed_{seed}_summary.json'
    rp.write_text(json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf8')
    report['runs'].append(summary);report['new_native_photon_likelihood_calls']=sum(row['new_photon_calls'] for row in report['runs'])
    report['current_seed']=None;report['completed_draws_current']=0
    saved_report(report)
    print('F91V2_NATIVE_SEED_RESULT',json.dumps({'seed':seed,'ESS':prefixes[-1]['ESS'],
       'maxW':prefixes[-1]['max_weight_fraction'],'logI':prefixes[-1]['log_conditional_integral'],'new_calls':newcalls}),flush=True)
if len(report['runs'])==4:
    rr=report['runs'];scores=[x['diagnostics']['log_conditional_integral'] for x in rr]
    gates={'ESS_min_each':all(x['diagnostics']['ESS']>=100 for x in rr),
        'maxW_max_each':all(x['diagnostics']['max_weight_fraction']<=.05 for x in rr),
        'phase_ESS_min_each':all(all(p['ESS']>=30 for p in x['diagnostics']['phase_partitions']) for x in rr),
        'half_256_512_logI_drift_max_each':all(abs(x['prefixes'][1]['log_conditional_integral']-x['prefixes'][2]['log_conditional_integral'])<=.1 for x in rr),
        'between_seed_logI_range_max':max(scores)-min(scores)<=.2}
    report['original_prespecified_gates']=gates
    report['status']='PASS_ALL_FOUR_FRESH_NATIVE_SEEDS' if all(gates.values()) else 'FAIL_FRESH_NATIVE_SAMPLER_NOT_ACCEPTED'
    saved_report(report)
    print('F91V2_FINAL',json.dumps({'status':report['status'],'gates':gates,
      'real_calls':report['new_native_photon_likelihood_calls'],'report_sha256':sha(reportpath)}),flush=True)
    if not all(gates.values()):sys.exit(2)


