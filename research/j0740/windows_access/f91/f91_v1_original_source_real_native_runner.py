from __future__ import annotations
import hashlib,importlib.util,json,math,os,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
NATIVE=ROOT/'native_prior'; REC=ROOT/'records'/'A01.01.51'/'PSR_J0740+6620'; OUT=ROOT/'evidence'/'native_photon'
for dep in ['six_unpacked','wrapt_unpacked']:
    sys.path.insert(0,str(NATIVE/'runtime-deps'/dep))
sys.path.insert(0,str(NATIVE))
import full_bootstrap as boot
xpsi=boot.xpsi
# Suppress only the source runner's already-completed embedded reference check;
# the unchanged likelihood is called below for every fresh held-out nuisance draw.
original_check=xpsi.Likelihood.check
xpsi.Likelihood.check=lambda *args,**kwargs: None
model_dir=NATIVE/'real-model';sys.path.insert(0,str(model_dir));old_cwd=Path.cwd();os.chdir(model_dir)
config=model_dir/'config_postprocess_J0740_gamma.ini'
sys.argv=['j0740_tailpatch_validation','@'+str(config)]
source=model_dir/'main_lp40k_Xse001_Dfix.py';spec=importlib.util.spec_from_file_location('j0740_tailpatch_native_model',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
xpsi.Likelihood.check=original_check
likelihood=module.likelihood
os.chdir(old_cwd)
from scipy.special import ndtr,ndtri
from scipy.stats import qmc,truncnorm
from temperature_coupling import Coupling,TransportProposal
from conditional_proposal import condition
from normalized_source_prior import RLO,RHI
from conditional_tail_patch import ConditionalTailPatchedProposal
from probit_proposal import log_phi
from weight_diagnostics import summarize

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
M,R=2.073,15.26
fixed=np.asarray([truncnorm.cdf(M,-5,5,loc=2.082,scale=.0703),(R-RLO)/(RHI-RLO)])
fixed_z=ndtri(fixed)
model_path=OUT/'temperature_transport_K48_local.npz';b=np.load(model_path);flow=Coupling(b['coupling_shift'],b['coupling_scale'],b['coupling_coef'])
ww,mm,cc=condition(b['weights'],b['means'],b['covs'],fixed_z);base=TransportProposal(ww,mm,cc,flow,fixed=fixed_z)
design=json.loads((REC/'J0740_15p26_CONDITIONAL_TAIL_PATCH_DESIGN_20261121.json').read_text())
assert design['base_model_sha256']==sha(model_path) and design['fresh_validation_seeds']==[211301,211303,211307,211311]
proposal=ConditionalTailPatchedProposal(base,flow,fixed_z,np.asarray([x['center_w_nuisance'] for x in design['tail_centers']]),np.asarray(design['selected_covariances']),design['epsilon'],design['df'])
assert proposal.epsilon==0.1 and sha(REC/'J0740_15p26_CONDITIONAL_TAIL_PATCH_DESIGN_20261121.json')=='50477db36217448177ef489980b395d6a92f37ec2409f2187b3420a0267bff82'
support=float(__import__('support_normalization').nuisance_acceptance())
results=[];eval_hashes=[]
for seed in design['fresh_validation_seeds']:
    seed=int(seed);started=time.monotonic();cache=OUT/f'MR_anchor_2_tailpatch_seed_{seed}_evals_local.jsonl';cached={}
    if cache.exists():
        for line in cache.read_text().splitlines():
            e=json.loads(line);assert e['index'] not in cached;cached[e['index']]=e
    unit=qmc.Sobol(17,scramble=True,seed=seed).random_base2(9);z=proposal.from_unit(unit);logq=proposal.logpdf(z)
    if cached:
        assert all(i<512 and np.max(np.abs(np.asarray(cached[i]['z'])-z[i]))<1e-12 for i in cached)
    lw=[];reasons=[];calls=0
    for i,zi in enumerate(z):
        if i in cached:e=cached[i]
        else:
            u=ndtr(zi);p=likelihood.prior.inverse_sample(np.r_[fixed,u]);reason='SOURCE_SUPPORT';ll=None
            if np.isfinite(likelihood.prior()):
                calls+=1;value=float(likelihood(p,reinitialise=True,force=True))
                if not math.isfinite(value):raise RuntimeError('nonfinite source likelihood')
                if value>-1e80:ll=value;reason='FINITE'
                else:reason='RATE_FLOOR'
            e={'index':i,'z':zi.tolist(),'logL':ll,'reason':reason,'model_sha256':design['frozen_model_sha256'],'tail_proposal_sha256':sha(REC/'J0740_15p26_CONDITIONAL_TAIL_PATCH_DESIGN_20261121.json'),'fixed_mass_radius':[M,R],'seed':seed}
            with cache.open('a',encoding='utf-8') as f:f.write(json.dumps(e,allow_nan=False,separators=(',',':'))+'\n')
        assert e['model_sha256']==design['frozen_model_sha256'] and e['fixed_mass_radius']==[M,R] and e['seed']==seed
        ll=-np.inf if e['logL'] is None else float(e['logL']);reasons.append(e['reason']);lw.append(ll+float(log_phi(zi))-math.log(support)-float(logq[i]))
        if (i+1)%128==0:print(json.dumps({'seed':seed,'draws':i+1,'new_photon_calls':calls,**summarize(lw,z[:i+1])}),flush=True)
    lw=np.asarray(lw);prefixes=[{'draws':n,**summarize(lw[:n],z[:n])} for n in [128,256,512]]
    result={'status':'FRESH_IID_CONDITIONAL_TAIL_PATCH_VALIDATION','seed':seed,'draws':512,'mass_radius':[M,R],'frozen_base_model_sha256':sha(model_path),'frozen_design_sha256':sha(REC/'J0740_15p26_CONDITIONAL_TAIL_PATCH_DESIGN_20261121.json'),'proposal_epsilon':proposal.epsilon,'proposal_df':proposal.df,'tail_kernel_count':len(proposal.kernels),'new_photon_calls':calls,'reason_counts':{k:reasons.count(k) for k in sorted(set(reasons))},'diagnostics':summarize(lw,z),'prefixes':prefixes,'weights_clipped':False,'valid_draws_removed':False,'source_prior_or_likelihood_changed':False,'elapsed_seconds':time.monotonic()-started,'EOS_Bayes':'NOT_RUN'}
    out=OUT/f'MR_anchor_2_tailpatch_seed_{seed}_512_local.npz';np.savez_compressed(out,z=z,logweights=lw)
    rp=OUT/f'MR_anchor_2_tailpatch_seed_{seed}_512_local.json';rp.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    results.append(result);eval_hashes.append({'seed':seed,'evals_bytes':cache.stat().st_size,'evals_sha256':sha(cache),'npz_bytes':out.stat().st_size,'npz_sha256':sha(out),'summary_bytes':rp.stat().st_size,'summary_sha256':sha(rp)})
    print(json.dumps({'seed':seed,'complete':True,'ESS':result['diagnostics']['ESS'],'max_weight':result['diagnostics']['max_weight_fraction'],'logI':result['diagnostics']['log_conditional_integral'],'min_phase_ESS':min(x['ESS'] for x in result['diagnostics']['phase_partitions']),'new_calls':calls}),flush=True)
logI=[r['diagnostics']['log_conditional_integral'] for r in results]
miness=min(r['diagnostics']['ESS'] for r in results);maxw=max(r['diagnostics']['max_weight_fraction'] for r in results);minphase=min(x['ESS'] for r in results for x in r['diagnostics']['phase_partitions']);drift=max(abs(r['prefixes'][1]['log_conditional_integral']-r['prefixes'][2]['log_conditional_integral']) for r in results)
gates={'ESS_per_run_min':miness>=100,'max_weight_fraction_max':maxw<=.05,'phase_ESS_each_min':minphase>=30,'between_run_log_integral_spread_max':max(logI)-min(logI)<=.2,'256_to_512_log_integral_drift_max':drift<=.1}
report={'schema':'J0740_15p26_CONDITIONAL_TAIL_PATCH_FRESH_VALIDATION_v1','date':'2026-11-21','status':'PASS' if all(gates.values()) else 'FAIL','fixed_MR':[M,R],'proposal_design':str((REC/'J0740_15p26_CONDITIONAL_TAIL_PATCH_DESIGN_20261121.json').relative_to(ROOT)),'frozen_design_sha256':sha(REC/'J0740_15p26_CONDITIONAL_TAIL_PATCH_DESIGN_20261121.json'),'source_prior_model_code_hashes':json.loads((OUT/'model_source_manifest.json').read_text()),'xpsi_version':xpsi.__version__,'nuisance_support_normalization':support,'independent_seeds':design['fresh_validation_seeds'],'draws_per_seed':512,'predeclared_thresholds':{'ESS_per_run_min':100,'max_weight_fraction_max':.05,'phase_ESS_each_min':30,'between_run_log_integral_spread_max':.2,'256_to_512_log_integral_drift_max':.1},'metrics':{'min_ESS':miness,'max_weight':maxw,'min_phase_ESS':minphase,'log_integral_spread':max(logI)-min(logI),'max_256_to_512_drift':drift},'gates':gates,'runs':[{k:r[k] for k in ['seed','draws','diagnostics','prefixes','reason_counts','new_photon_calls','elapsed_seconds']} for r in results],'local_raw_artifact_hashes':eval_hashes,'total_new_photon_calls':sum(r['new_photon_calls'] for r in results),'source_prior_or_likelihood_changed':False,'weights_clipped_or_valid_draws_removed':False,'all_MR_domain_certified':False,'EOS_Bayes':'NOT_RUN','scope':'Only fixed (2.073 M_sun,15.26 km) conditional nuisance integral; no EOS curve, full M,R, or evidence claim'}
report_path=REC/'J0740_15p26_CONDITIONAL_TAIL_PATCH_FRESH_VALIDATION_20261121.json';report_path.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'status':report['status'],'gates':gates,'metrics':report['metrics'],'report_bytes':report_path.stat().st_size,'report_sha256':sha(report_path),'raw_eval_hashes':eval_hashes},indent=2),flush=True)
if report['status']!='PASS':raise SystemExit(1)

