"""F39: direct rotating RNS roots + F38 Salmi source relative likelihood integration.

Conditional diagnostic only. Mass prior is explicitly the source radio-mass prior
conditioned on a stated mass window. No automatic EOS model selection claim.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
from scipy.interpolate import RegularGridInterpolator
from scipy.stats import norm

M_MIN, M_MAX = 1.92, 2.15
M_MU, M_SIG = 2.082, 0.0703
SOURCE_F38_GRID_HASH = {
    'posterior_prior_ratio_weighted_0.015_0.20.npz': '7eb582859e42eb2700b75ec584af20e9cb10ed10449375b838794be200db1fe6',
    'posterior_prior_ratio_weighted_0.025_0.35.npz': 'c024fb8347992f78a22d13585372ee862be596f16cc668a661c41503d89e6fa4',
    'posterior_prior_ratio_weighted_0.040_0.50.npz': '4de295e3c64d3ccebff185f3e14f3d4ab487cc4a2c36beb780d68f8501c78ad9',
    'posterior_prior_ratio_resampled_0.015_0.20.npz': 'ab9326b7e6fbf4e8147a07bcce5117e3eb8b1873520c2f502798a426ab4b0926',
    'posterior_prior_ratio_resampled_0.025_0.35.npz': '9f16ef601df4b8ede0c90579a6bfa67bd4421a23f7798455b6ff8f34f6040166',
    'posterior_prior_ratio_resampled_0.040_0.50.npz': '7e1bcb027421ac8a2f5a6343a36a32137bfb315c1a27663c650a00c45d7eacdd',
}
F38_META_SHA = '0e7e7aeea605ea3739808022374fdfb35c2ff5eb270fe04554848352e4f0360a'
RNS_EOS_GIT_BLOB_SHA = '537783f0d259bc0d59a1c4b39e6ae402eeaa7379'
SPIN_HZ = 346.536369


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def norm_radio_mass_window(lo=M_MIN, hi=M_MAX):
    if not (M_MU-5*M_SIG <= lo < hi <= M_MU+5*M_SIG):
        raise ValueError('Mass interval outside original radio prior')
    full = norm.cdf(5)-norm.cdf(-5)
    return (norm.cdf((hi-M_MU)/M_SIG)-norm.cdf((lo-M_MU)/M_SIG))/full


def normalized_window_pdf(m):
    return norm.pdf((np.asarray(m)-M_MU)/M_SIG)/(M_SIG*(norm.cdf((M_MAX-M_MU)/M_SIG)-norm.cdf((M_MIN-M_MU)/M_SIG)))


def read_likelihood(path):
    path=Path(path)
    expect=SOURCE_F38_GRID_HASH.get(path.name)
    if not expect or sha256(path)!=expect:
        raise ValueError('F38_SOURCE_GRID_SHA_MISMATCH')
    with np.load(path,allow_pickle=False) as a:
        mass=a['mass_centres'].astype(float)
        radius=a['radius_centres_km'].astype(float)
        values=a['relative_likelihood_L_over_Z'].astype(float)
        support=a['hard_source_support'].astype(bool)
        prior=a['source_effective_prior'].astype(float)
    if mass.shape!=(401,) or radius.shape!=(581,) or values.shape!=(401,581):
        raise ValueError('F38 grid shape mismatch')
    if not (np.isfinite(values).all() and (values>=0).all()
            and np.all(values[~support]==0) and np.all(prior[~support]==0)):
        raise ValueError('F38 grid invalid')
    return mass,radius,values,support,prior


def analyze_grid(path,curve):
    mass,radius,L,support,prior=read_likelihood(path)
    cm=np.array([x['target_mass_msun'] for x in curve],dtype=float)
    cr=np.array([x['radius_eq_km'] for x in curve],dtype=float)
    if np.any(np.diff(cm)<=0) or cm[0]>M_MIN+1e-6 or cm[-1]<M_MAX-1e-6:
        raise ValueError('Missing mass coverage')
    xy=np.stack([cm,cr],axis=1)
    l_itp=RegularGridInterpolator((mass,radius),L,method='linear',bounds_error=True)
    # Never use extrapolated likelihood: all 4 corners of interpolating cell
    # must lie within the exact source hard-support mask.
    i=np.searchsorted(mass,cm,side='right')-1
    j=np.searchsorted(radius,cr,side='right')-1
    if np.any(i<0) or np.any(j<0) or np.any(i>=len(mass)-1) or np.any(j>=len(radius)-1):
        raise ValueError('Curve outside F38 grid')
    if not (support[i,j]&support[i+1,j]&support[i,j+1]&support[i+1,j+1]).all():
        raise ValueError('Curve touches prior hard-support mask boundary')
    like=l_itp(xy)
    if not np.isfinite(like).all() or np.any(like<0):
        raise ValueError('Invalid interpolated source likelihood')
    q=normalized_window_pdf(cm)
    # Quadrature on full and every-other actual RNS solution. No mass extrapolation.
    full=float(simpson(q*like,x=cm))
    coar=float(simpson((q*like)[::2],x=cm[::2]))
    normfull=float(simpson(q,x=cm))
    # Saturated flexible R-at-each-M ceiling; a diagnostic, NOT a physical EOS.
    maxL=np.max(L,axis=1)
    max_itp=np.interp(cm,mass,maxL)
    ceil=float(simpson(q*max_itp,x=cm))
    if not(0<full<=ceil*1.05 and abs(normfull-1)<1e-4):
        raise ValueError('Conditional mass prior / evidence integral invalid')
    return {'curve_conditional_L_over_Z':full,'coarse_simpson_L_over_Z':coar,
            'quadrature_relative_percent':100*(coar/full-1),
            'radio_window_normalization_check':normfull,
            'flexible_radius_envelope_L_over_Z':ceil,
            'model_to_flexible_envelope_fraction':full/ceil,
            'point_likelihood_range':[float(like.min()),float(like.max())],
            'interpolation_verified_interior':True}


def run(args):
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    original=args.table
    if not original.is_file():raise FileNotFoundError('Original source causal APR4 RNS table missing')
    # Pin to the source Git blob rather than reprocessing the EOS table.
    import subprocess
    blob=subprocess.run(['git','hash-object',str(original)],capture_output=True,text=True,check=True).stdout.strip()
    if blob!=RNS_EOS_GIT_BLOB_SHA:
        raise ValueError(f'CAUSAL_APR4_TABLE_GIT_BLOB_MISMATCH:{blob}')
    report={'schema':'J0740_F39_source_marginal_conditional_eos_curve_v1',
            'status':'RUNNING_FAIL_CLOSED','experimental_eos':'LALSuite 7.26.4 APR4 native causal completion',
            'original_APR4_acausal_source_unchanged':True,
            'source_RNS_EOS_git_blob':blob,'source_RNS_EOS_sha256':sha256(original),
            'original_Salmi_F38_source':'SHA256 verified 40.605.003-byte published posterior, via F38 pinned NPZ',
            'model_physical_mu0':'NOT_ESTABLISHED',
            'model_global_dynamical_stability':'NOT_ESTABLISHED',
            'seven_EOS_physical_Bayes_factors':'NOT_RUN',
            'mass_prior':'Source radio gaussian truncated +/-5 sigma, re-introduced once after posterior/prior ratio; conditioned 1.92-2.15 Msun',
            'radio_mass_probability_in_window':norm_radio_mass_window(),
            'mass_window_msun':[M_MIN,M_MAX],'source_15D_nuisance':'Inherited approximate marginalized ratio from F38, not compiled photon fit',
            'fixed_spin_hz':SPIN_HZ,'curve':[],'likelihood_grids':{}}
    def save():out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    save()
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'rotating_gr'))
    import precise_apr4_mass_spin_root as solver
    masses=np.linspace(M_MIN,M_MAX,25)
    # The source RNS solved center starts at 2.073, then walks to adjacent masses.
    anchor=(1.7593486615105065,.9861881190400344)
    targets=sorted(masses,key=lambda m:abs(m-2.073))
    found={}
    for m in targets:
        nearest=min(found.values(),key=lambda x:abs(x['target_mass_msun']-m)) if found else None
        seed=(nearest['central_energy_density_g_cm3']/1e15,nearest['axis_ratio']) if nearest else anchor
        solver.TARGET_MASS_MSUN=float(m)
        trace_fail=[]
        for s in (seed,anchor,(1.65,.987),(1.95,.985)):
            try:
                result=solver.solve_fixed_mf(
                    lambda ec, ratio:solver.run_model(args.binary_fine,original,ec,ratio),s,
                    max_iterations=23)
                break
            except Exception as exc:
                trace_fail.append({'seed':list(s),'exception':str(exc)[:260]})
        else:
            report['status']='FAIL_RNS_MASS_ROOT';report['failed_mass_msun']=float(m)
            report['root_failures']=trace_fail;save()
            raise RuntimeError('Causal APR4 RNS root fail at mass '+str(m))
        if abs(result['mass_msun']-m)>solver.MASS_TOL_MSUN or abs(result['spin_hz']-SPIN_HZ)>solver.SPIN_TOL_HZ:
            raise ValueError('Fixed spin or mass tolerance failure')
        rec={k:result[k] for k in ['mass_msun','spin_hz','radius_eq_km','central_energy_density_g_cm3','axis_ratio']}
        rec['target_mass_msun']=float(m)
        rec['root_seed']=list(s)
        rec['evaluations']=len(result['root_trace'])
        found[round(float(m),9)]=rec
        report['curve']=sorted(found.values(),key=lambda x:x['target_mass_msun'])
        save()
        print('ROOT_OK',round(float(m),6),round(rec['radius_eq_km'],7),len(result['root_trace']),flush=True)
    curve=report['curve']
    dens=np.array([v['central_energy_density_g_cm3'] for v in curve])
    if not np.all(np.diff(dens)>0) or np.max(dens)>=2.6e15:
        raise ValueError('Full curve violates conservative sampled F37 fixed-J turning bound')
    # Independent coarse spatial mesh check: five pre-registered masses.
    for idx in [0,6,12,18,24]:
        a=curve[idx];solver.TARGET_MASS_MSUN=a['target_mass_msun']
        s=(a['central_energy_density_g_cm3']/1e15,a['axis_ratio'])
        b=solver.solve_fixed_mf(lambda ec,ratio:solver.run_model(args.binary_coarse,original,ec,ratio),s,max_iterations=23)
        a['coarse_mesh_radius_km']=b['radius_eq_km']
        a['coarse_minus_fine_radius_km']=b['radius_eq_km']-a['radius_eq_km']
        if abs(a['coarse_minus_fine_radius_km'])>=0.03:raise ValueError('RNS mesh fails tolerance')
        save()
    report['max_coarse_fine_delta_km']=max(abs(x.get('coarse_minus_fine_radius_km',0)) for x in curve)
    for filename in SOURCE_F38_GRID_HASH:
        p=args.f38/filename
        report['likelihood_grids'][filename]=analyze_grid(p,curve)
        save()
        print('INTEGRAL_OK',filename,report['likelihood_grids'][filename]['curve_conditional_L_over_Z'],flush=True)
    w=[x for k,x in report['likelihood_grids'].items() if '_weighted_' in k]
    e=[x for k,x in report['likelihood_grids'].items() if '_resampled_' in k]
    report['weighted_evidence_range']=[min(x['curve_conditional_L_over_Z'] for x in w),max(x['curve_conditional_L_over_Z'] for x in w)]
    report['max_quadrature_delta_percent']=max(abs(x['quadrature_relative_percent']) for x in report['likelihood_grids'].values())
    report['max_weighted_resampled_pct']=max(100*abs(report['likelihood_grids'][k.replace('_weighted_','_resampled_')]['curve_conditional_L_over_Z']/v['curve_conditional_L_over_Z']-1) for k,v in report['likelihood_grids'].items() if '_weighted_' in k)
    report['status']='PASS_CONDITIONAL_APR4_SOURCE_MARGINALIZED_CURVE_PROBE_NOT_SEVEN_EOS_BAYES'
    save()
    print('RESULT',json.dumps({'status':report['status'],'weighted_evidence_range':report['weighted_evidence_range'],'max_grid_check_pct':report['max_weighted_resampled_pct'],'max_quad_pct':report['max_quadrature_delta_percent'],'mass_window_prior_fraction':report['radio_mass_probability_in_window']}),flush=True)
    return report


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--table',type=Path,required=True)
    ap.add_argument('--binary-fine',type=Path,required=True)
    ap.add_argument('--binary-coarse',type=Path,required=True)
    ap.add_argument('--f38',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    run(args)

if __name__=='__main__':main()