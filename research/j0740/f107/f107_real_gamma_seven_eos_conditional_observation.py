#!/usr/bin/env python3
"""Source SHA-locked Salmi-2024 GAMMA NICER/XMM posterior vs seven true C/RNS EOS M-R paths.

A new observational POSTERIOR-COMPATIBILITY sensitivity check, *not* a photon-native
likelihood, nor absolute Bayes factors. Correctly conditions published gamma posterior
on mass before inserting one chosen independent radio mass prior (no double counting).
No F38 STU likelihood grid or synthetic stellar curves are used.
"""
import argparse,base64,hashlib,io,json,math,zipfile
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.interpolate import PchipInterpolator,RegularGridInterpolator
from scipy.stats import norm
from scipy.integrate import simpson

PUB_GIT_BLOB_SHA1='8a5adb339699ea1065aa858bdab406de11b22f72'
MODELS=('APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2')
RADIO_MASS_MEAN=2.082
RADIO_MASS_SD=.0703
GAMMA_FILENAME='J07406620_amsterdam_gamma_NICERXMM_equal_weights_recent.npz'
M_BOUNDS=(1.2,3.0)
R_BOUNDS=(5.0,20.0)
DM=.005
DR=.025
M_GRID=np.arange(M_BOUNDS[0]+DM/2,M_BOUNDS[1],DM)
R_GRID=np.arange(R_BOUNDS[0]+DR/2,R_BOUNDS[1],DR)
RADIO_M_GRID=np.linspace(RADIO_MASS_MEAN-5*RADIO_MASS_SD,RADIO_MASS_MEAN+5*RADIO_MASS_SD,1201)
RADIO_DENSITY=norm.pdf(RADIO_M_GRID,loc=RADIO_MASS_MEAN,scale=RADIO_MASS_SD)
RADIO_DENSITY/=simpson(RADIO_DENSITY,x=RADIO_M_GRID)


def sha256_bytes(b):return hashlib.sha256(b).hexdigest()
def git_blob_sha1(b):return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()

def read_gamma(p):
    p=Path(p);raw=p.read_bytes()
    actual=git_blob_sha1(raw)
    if actual!=PUB_GIT_BLOB_SHA1:raise ValueError('JESTER_PUBLISHED_GAMMA_BLOB_SHA_MISMATCH '+actual)
    if not zipfile.is_zipfile(io.BytesIO(raw)):raise ValueError('GAMMA_NOT_NPZ')
    with np.load(io.BytesIO(raw),allow_pickle=False) as z:
        if not {'mass','radius'}.issubset(z.files):raise ValueError('GAMMA_MASS_RADIUS_KEYS_MISSING')
        m=np.asarray(z['mass'],float);r=np.asarray(z['radius'],float)
    if m.ndim!=1 or len(m)<5000 or r.shape!=m.shape or not np.isfinite(m).all() or not np.isfinite(r).all():
        raise ValueError('GAMMA_PUBLISHED_SAMPLES_BAD')
    inside=(m>M_BOUNDS[0])&(m<M_BOUNDS[1])&(r>R_BOUNDS[0])&(r<R_BOUNDS[1])
    if np.count_nonzero(inside)!=len(m):raise ValueError('GAMMA_SAMPLES_OUTSIDE_PREDECLARED_OBSERVATION_BOUNDS')
    return m,r,{'filename':GAMMA_FILENAME,'git_blob_sha1':actual,'file_sha256':sha256_bytes(raw),'n_equal_weight_samples':int(len(m)),
                'sample_mass_quantiles_msun':np.quantile(m,[.025,.16,.5,.84,.975]).tolist(),
                'sample_radius_quantiles_km':np.quantile(r,[.025,.16,.5,.84,.975]).tolist(),
                'sample_corr_mass_radius':float(np.corrcoef(m,r)[0,1])}


def original_seven_paths(root):
    root=Path(root)
    mani=json.loads((root/'F38_rotating_massline_witness_manifest.json').read_text())
    if mani.get('source_2d_F38_archive_SHA256')!='4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307':raise ValueError('STU_SOURCE_WITNESS_MANIFEST_CHANGED')
    if set(mani['models'])!=set(MODELS):raise ValueError('NOT_SEVEN_GENUINE_C_MODELS')
    result={}
    for key in MODELS:
        info=mani['models'][key]
        by=base64.b64decode((root/info['file']).read_text().strip(),validate=True)
        if sha256_bytes(by)!=info['decoded_npz_sha256']:raise ValueError('REAL_C_WITNESS_SHA_CHANGED '+key)
        with np.load(io.BytesIO(by),allow_pickle=False) as z:
            m=np.asarray(z['mass_msun'],float);r=np.asarray(z['radius_eq_km'],float)
        if m.shape!=(1001,) or r.shape!=m.shape or not(np.diff(m)>0).all() or not(np.isfinite(r).all()):
            raise ValueError('INVALID_SOURCE_C_MASSLINE '+key)
        # Do NOT use old source STU support mask here!  New gamma analysis has different geometry/prior.
        result[key]={'curve':PchipInterpolator(m,r,extrapolate=False),
                     'minM':float(m[0]),'maxM':float(m[-1]),'source_C_witness_sha256':sha256_bytes(by),
                     'M2p073_rotating_radius_km':float(np.interp(2.073,m,r)) if m[0]<=2.073<=m[-1] else None}
    return result


def conditional_posterior_surface(m,r,bandwidth_m,bandwidth_r):
    counts,*_=np.histogram2d(m,r,bins=[np.arange(M_BOUNDS[0],M_BOUNDS[1]+DM*.5,DM),np.arange(R_BOUNDS[0],R_BOUNDS[1]+DR*.5,DR)])
    if counts.shape!=(len(M_GRID),len(R_GRID)):raise ValueError('HISTOGRAM_GRID_BAD')
    smooth=gaussian_filter(counts,(bandwidth_m/DM,bandwidth_r/DR),mode='constant',truncate=4.0)
    marginal=smooth.sum(axis=1)*DR
    # p(R|M, gamma posterior) = p(M,R|D)/p(M|D); removes original radio mass prior once.
    cond=smooth / np.maximum(marginal[:,None],np.finfo(float).tiny)
    if not np.isfinite(cond).all() or (cond<0).any():raise ValueError('KDE_NOT_VALID')
    return RegularGridInterpolator((M_GRID,R_GRID),cond,bounds_error=False,fill_value=0.0),cond


def conditional_radio_mass_score(interp,model):
    mm=RADIO_M_GRID
    allowed=(mm>=model['minM'])&(mm<=model['maxM'])
    radii=np.full(len(mm),np.nan)
    radii[allowed]=model['curve'](mm[allowed])
    pts=np.column_stack([mm[allowed],radii[allowed]])
    pdens=np.zeros(len(mm));pdens[allowed]=interp(pts)
    pdens=np.maximum(pdens,0)
    support=float(simpson(RADIO_DENSITY*allowed.astype(float),x=mm))
    score=float(simpson(RADIO_DENSITY*pdens,x=mm))
    if not (0<=support<=1+1e-6 and math.isfinite(score) and score>=0):raise ValueError('BAD_SCORE')
    return {'conditional_gamma_posterior_radio_mass_average_per_km':score,
            'original_C_mass_support_radio_probability':support,
            'score_divided_by_mass_support_FOR_DIAGNOSTICS_ONLY':score/support if support>0 else None,
            'radius_at_2p073_rotating_km':model['M2p073_rotating_radius_km'],
            'source_C_witness_sha256':model['source_C_witness_sha256'],
            'observed_gamma_at_2p073_source_C_radius_per_km':float(interp([[2.073,model['M2p073_rotating_radius_km']]])[0]) if model['M2p073_rotating_radius_km'] else None}


def run(gamma,witness,out):
    m,r,source=read_gamma(gamma)
    paths=original_seven_paths(witness)
    scenarios={}
    for bm,br in ((.025,.25),(.035,.35),(.05,.5)):
        interp,conditional=conditional_posterior_surface(m,r,bm,br)
        scores={name:conditional_radio_mass_score(interp,paths[name]) for name in MODELS}
        ranks=sorted(MODELS,key=lambda name:-scores[name]['conditional_gamma_posterior_radio_mass_average_per_km'])
        row=conditional[int(np.argmin(abs(M_GRID-2.073))),:]
        # Normalize conditional row; do not invent posterior radius prior corrections.
        density=row/(row.sum()*DR)
        cdf=np.cumsum(density)*DR
        q=[float(np.interp(v,cdf,R_GRID)) for v in (.16,.5,.84)]
        scenarios[f'bandwidth_mass_{bm:.3f}_radius_{br:.3f}']={'bandwidth_mass_msun':bm,'bandwidth_radius_km':br,
                  'scores':scores,'gamma_conditional_posterior_radius_quantiles_at_2p073_msun_km':q,
                  'gamma_conditional_posterior_radius_mode_at_2p073_msun_km':float(R_GRID[np.argmax(density)]),
                  'ranking_PURE_POSTERIOR_COMPATIBILITY_NOT_BAYES':ranks}
    names=list(scenarios)
    a={x:scenarios[names[0]]['ranking_PURE_POSTERIOR_COMPATIBILITY_NOT_BAYES'].index(x)+1 for x in MODELS}
    c={x:scenarios[names[-1]]['ranking_PURE_POSTERIOR_COMPATIBILITY_NOT_BAYES'].index(x)+1 for x in MODELS}
    res={'schema':'J0740_F107_GENUINE_2026_JESTER_SALMI2024_GAMMA_7_ORIGINAL_ROTATING_C_POSTERIOR_COMPATIBILITY_V1',
         'source_gamma_JESTER':source,
         'source_original_7_C_RNS_F38_witness_manifest':'F38_rotating_massline_witness_manifest.json',
         'observational_hotspot_model':'GAMMA (JESTER Salmi 2024 source), deliberately NOT old STU_NICER_XMM_hr',
         'source_native_XPSI_photon_calls':0,'this_is_full_seven_EOS_photon_Bayes':False,
         'statistical_quantity':'mass prior weighted gamma POSTERIOR CONDITIONAL p(R|M,data) along each source-locked 7 rotating 346.536Hz C equilibrium curve, not prior-corrected gamma photon likelihood',
         'double_count_guard':'Divide gamma joint posterior by its OWN M marginal to condition on mass; use external N(2.082,0.0703) radio mass prior once; original gamma source radius+geometric priors remain and are NOT removed',
         'physics_guard':'Neither this observational statistic nor a high score certifies EOS physical causality or dynamic stability; F79 disqualified 294/323 historic stars.',
         'bandwidth_sensitivity':scenarios,
         'ranking_changed_across_smoothing':any(a[x]!=c[x] for x in MODELS),
         'original_matter_models':list(MODELS),
         'model_prior_posterior_probabilities':'NOT_COMPUTABLE_FROM_GAMMA_POSTERIOR_ALONE',
         'validated_gamma_native_photon_Bayes':'NOT_RUN',
         'seven_EOS_full_native_photon_Bayes':'NOT_RUN',
         'user_windows_original_photon_archive':'REMAINS_OFFLINE_UNTOUCHED'}
    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(res,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'gamma_n':len(m),'gamma_sha256':source['file_sha256'],
        'scenarios':{k:{'ranks':v['ranking_PURE_POSTERIOR_COMPATIBILITY_NOT_BAYES'],
                        'score':{z:round(v['scores'][z]['conditional_gamma_posterior_radio_mass_average_per_km'],6) for z in MODELS},
                        'R_conditional_68':v['gamma_conditional_posterior_radius_quantiles_at_2p073_msun_km']} for k,v in scenarios.items()},
        'overall_mode':'CONDITIONAL_GAMMA_OBSERVATIONAL_POSTERIOR_NOT_PHOTON_BAYES'},indent=2))
    return res

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--gamma',type=Path,required=True)
    p.add_argument('--original-seven',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    run(a.gamma,a.original_seven,a.out)
