#!/usr/bin/env python3
"""PSR J0740+6620: safe Bayesian EOS *integration kernel* and data preflight.

IMPORTANT: This tool does NOT manufacture the X-PSI marginal effective prior or
rotating-star EOS curves. Scientific scores are DISABLED until both are supplied.

Notation: q(M,R|D) = observed M,R posterior; pi_X(M,R) = X-PSI *marginal*
analysis prior, including all nuisance/selection/geometry support (not merely
radio mass Gaussian); pi_T(M) = target mass prior, included exactly once.
For a physically computed rotating EOS R_eq(M,spin):
    Z(EOS) / Z_X ∝ integral dM pi_T(M) q(M,R_eq(M)|D)/pi_X(M,R_eq(M))
The arbitrary Z_X cancels when normalizing EOS weights within each analysis.
If Amsterdam and Maryland overlap in photons, NEVER multiply their likelihoods.
We only permit a mixture of separately normalized EOS posteriors.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.interpolate import RegularGridInterpolator
from scipy.special import logsumexp

EXPECTED_SHA256 = '4587a7d71aca7b561e5cf22623e3f0e2d80a6c54add0ecb7abc0389d705e8d5b'
RADIO_MU, RADIO_SIGMA = 2.082, 0.0703

def sha256(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda: f.read(1024 * 1024), b''): h.update(c)
    return h.hexdigest()


def load_posterior(path: Path, expected_sha: str | None = None):
    if expected_sha and sha256(path) != expected_sha:
        raise ValueError('Posterior SHA-256 mismatch; refuse to use unverified source.')
    with np.load(path, allow_pickle=False) as a:
        m = np.asarray(a['mass'], dtype=float)
        r = np.asarray(a['radius'], dtype=float)
    if m.ndim != 1 or r.shape != m.shape or m.size < 50:
        raise ValueError('Mass/radius arrays not valid or not paired.')
    if not (np.all(np.isfinite(m)) and np.all(np.isfinite(r))
            and np.all(m > 0) and np.all(r > 0)):
        raise ValueError('Unphysical or nonfinite posterior values.')
    return m, r


def preflight(path: Path, check_sha=True):
    m, r = load_posterior(path, EXPECTED_SHA256 if check_sha else None)
    qs = lambda x: [float(z) for z in np.quantile(x, [0.16, 0.5, 0.84])]
    return {
        'source_file':path.name, 'sha256':sha256(path), 'count':int(m.size),
        'mass_quantiles_16_50_84_msun':qs(m),
        'radius_quantiles_16_50_84_km':qs(r),
        'radius_gt_16km_count':int(np.count_nonzero(r>16)),
        'derived_compactness_quantiles_16_50_84':qs(1.4766250385*m/r),
        'preflight':'PASS', 'eos_inference_status':'NOT_RUN: missing verified X-PSI effective prior and physical rotating EOS curves'
    }


def posterior_grid(m, r, mass_edges=None, radius_edges=None, smooth_bins=1.2, radius_boundary="truncate"):
    """Normalized 2D posterior density, not a likelihood. Histogram Gaussian smoothing is a numerical surrogate."""
    if not np.isfinite(smooth_bins) or smooth_bins <= 0: raise ValueError('smooth_bins must be positive')
    if radius_boundary not in ("truncate", "reflect"):
        raise ValueError("radius_boundary must be truncate or reflect")
    if mass_edges is None: mass_edges=np.linspace(1.70,2.42,181)
    # Salmi 2024 headline ST-U source prior has hard R_eq <= 16 km.
    # Do not smooth the source posterior into impossible R > 16 km bins.
    if radius_edges is None: radius_edges=np.linspace(8.0,16.0,257)
    mass_edges=np.asarray(mass_edges); radius_edges=np.asarray(radius_edges)
    if not np.all(np.diff(mass_edges)>0) or not np.all(np.diff(radius_edges)>0):
        raise ValueError('Grid edges must be strictly ascending')
    if np.mean((m>=mass_edges[0])&(m<=mass_edges[-1])&(r>=radius_edges[0])&(r<=radius_edges[-1]))<0.999:
        raise ValueError('Posterior grid misses >0.1% of sample points; increase range')
    counts, _, _ = np.histogram2d(m,r,bins=(mass_edges,radius_edges))
    dM=np.diff(mass_edges); dR=np.diff(radius_edges)
    if max(np.ptp(dM),np.ptp(dR))>1e-9: raise ValueError('Use equal-width bins for Gaussian smoothing')
    # Boundary sensitivity: truncated KDE versus reflected KDE at finite R support.
    # This is an estimator choice, NOT a reconstruction of the X-PSI effective prior.
    counts=gaussian_filter(counts, sigma=float(smooth_bins),
                           mode=('constant', 'reflect' if radius_boundary=='reflect' else 'constant'))
    density=counts/(counts.sum()*dM[0]*dR[0])
    return (mass_edges[:-1]+mass_edges[1:])/2, (radius_edges[:-1]+radius_edges[1:])/2, density


def normal_pdf(m, mu=RADIO_MU, sigma=RADIO_SIGMA):
    if sigma<=0: raise ValueError('sigma must be positive')
    x=(m-mu)/sigma
    return np.exp(-x*x/2)/(sigma*np.sqrt(2*np.pi))


def normalized_weights(log_evidence, model_logprior=None):
    """Return a *one-dimensional* EOS posterior with no accidental broadcasting."""
    log_evidence=np.asarray(log_evidence,dtype=float)
    if log_evidence.ndim!=1 or log_evidence.size==0:
        raise ValueError('EOS evidence must be a nonempty one-dimensional vector')
    if np.any(np.isnan(log_evidence)) or np.any(np.isposinf(log_evidence)):
        raise ValueError('Invalid EOS scores')
    if model_logprior is None:
        prior=np.full(log_evidence.shape,-np.log(log_evidence.size))
    else:
        prior=np.asarray(model_logprior,dtype=float)
        if prior.shape!=log_evidence.shape:
            raise ValueError('EOS model prior shape must exactly match evidence vector')
        if np.any(np.isnan(prior)) or np.any(np.isposinf(prior)):
            raise ValueError('Invalid EOS model log-prior')
    l=log_evidence+prior
    if not np.any(np.isfinite(l)):
        raise ValueError('No EOS with positive support')
    return np.exp(l-logsumexp(l))


def mixture_of_alternative_posteriors(group_posteriors, group_mixture_weights):
    """Mixture model on overlapping data; do not multiply group posteriors or raw uncalibrated evidence."""
    x=np.array(group_posteriors,dtype=float)
    w=np.array(group_mixture_weights,dtype=float)
    if x.ndim!=2 or w.shape!=(x.shape[0],) or not np.all(np.isfinite(x)) or np.any(x<0):
        raise ValueError('Invalid group posterior mixtures')
    if not np.allclose(x.sum(axis=1),1,atol=1e-8):raise ValueError('Normalize each group separately')
    if np.any(w<0) or not np.all(np.isfinite(w)) or w.sum()<=0: raise ValueError('Invalid mixture weights')
    return np.average(x,axis=0,weights=w)


def integrate_eos_curve(m_grid, r_grid, q_grid, prior_grid,
                        curve_mass, curve_equatorial_radius,
                        target_mass_pdf=None):
    """Integrate an EOS curve only over its intersections with the M-R grid.

    Geometric clipping is performed *per adjacent EOS segment*. Filtering
    invalid points and joining the remaining ones would invent unsupported
    curve intervals and overstate evidence. Densities are interpolated only
    inside the grid; no physical likelihood is inferred without audited inputs.
    """
    mg=np.asarray(m_grid,dtype=float); rg=np.asarray(r_grid,dtype=float)
    q=np.asarray(q_grid,dtype=float); pi=np.asarray(prior_grid,dtype=float)
    cm=np.asarray(curve_mass,dtype=float); cr=np.asarray(curve_equatorial_radius,dtype=float)
    if q.shape!=(mg.size,rg.size) or pi.shape!=q.shape or cm.shape!=cr.shape or cm.ndim!=1 or cm.size<5:
        raise ValueError('Input grid / EOS dimensions invalid')
    if not (np.all(np.isfinite(mg)) and np.all(np.isfinite(rg)) and
            np.all(np.diff(mg)>0) and np.all(np.diff(rg)>0) and
            np.all(np.isfinite(cm)) and np.all(np.isfinite(cr)) and
            np.all(np.diff(cm)>0)):
        raise ValueError('Mass and radius axes must be finite; mass axes must increase')
    if not (np.all(np.isfinite(q)) and np.all(np.isfinite(pi)) and np.all(q>=0) and np.all(pi>=0)):
        raise ValueError('Density contains nonfinite/negative values')

    q_at = RegularGridInterpolator((mg,rg),q,bounds_error=True)
    p_at = RegularGridInterpolator((mg,rg),pi,bounds_error=True)
    mass_spacing=float(np.min(np.diff(mg)))
    radius_spacing=float(np.min(np.diff(rg)))
    total=0.0
    supported_segments=0
    for i in range(len(cm)-1):
        # Parameterize a piecewise-linear physical EOS segment by t in [0,1].
        m0,m1=cm[i:i+2];r0,r1=cr[i:i+2]
        tlo,thi=0.0,1.0
        for lo,hi,p0,p1 in ((mg[0],mg[-1],m0,m1),(rg[0],rg[-1],r0,r1)):
            if p0==p1:
                if p0<lo or p0>hi:thi=-1.0;break
            else:
                ta,tb=sorted(((lo-p0)/(p1-p0),(hi-p0)/(p1-p0)))
                tlo=max(tlo,ta);thi=min(thi,tb)
        if thi<=tlo:continue
        dm=(m1-m0)*(thi-tlo);dr=(r1-r0)*(thi-tlo)
        # Resolve density-grid structure even if source EOS points are sparse.
        n=max(2,1+int(np.ceil(max(abs(dm)/mass_spacing,abs(dr)/radius_spacing))))
        tt=np.linspace(tlo,thi,n)
        xx=np.column_stack((m0+(m1-m0)*tt,r0+(r1-r0)*tt))
        # Avoid harmless roundoff pushing exact boundary crossings out of grid.
        xx[:,0]=np.clip(xx[:,0],mg[0],mg[-1])
        xx[:,1]=np.clip(xx[:,1],rg[0],rg[-1])
        Q=q_at(xx);P=p_at(xx)
        if np.any((Q>1e-12*q.max())&(P<=0)):
            raise ValueError('Source posterior has support where effective prior is ZERO. Check smoothing/boundaries.')
        ratio=np.divide(Q,P,out=np.zeros_like(Q),where=P>0)
        mpdf=normal_pdf(xx[:,0]) if target_mass_pdf is None else np.asarray(target_mass_pdf(xx[:,0]))
        if mpdf.shape!=ratio.shape or np.any(mpdf<0) or not np.all(np.isfinite(mpdf)):
            raise ValueError('Invalid target mass prior')
        total+=float(np.trapezoid(ratio*mpdf,xx[:,0]))
        supported_segments+=1
    if supported_segments==0:return -np.inf
    return float(np.log(total)) if total>0 else -np.inf


def load_prior_grid(path):
    """CSV with columns mass_msun,radius_km,pi_eff. Must be precomputed via X-PSI native prior MC and audited."""
    x=np.genfromtxt(path,delimiter=',',names=True)
    if set(x.dtype.names or ()) != {'mass_msun','radius_km','pi_eff'}:
        raise ValueError('Need ONLY columns mass_msun,radius_km,pi_eff')
    m=np.unique(x['mass_msun']); r=np.unique(x['radius_km'])
    if len(x)!=len(m)*len(r):raise ValueError('Prior grid is incomplete')
    from scipy.interpolate import RegularGridInterpolator
    grid=np.full((len(m),len(r)),np.nan)
    ii=np.searchsorted(m,x['mass_msun']);jj=np.searchsorted(r,x['radius_km'])
    if len(np.unique(ii*len(r)+jj))!=len(x):raise ValueError('Duplicated prior grid cell')
    grid[ii,jj]=x['pi_eff']
    if np.any(~np.isfinite(grid)) or np.any(grid<0):raise ValueError('Invalid prior grid')
    return m,r,grid


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--posterior',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--allow-other-sha',action='store_true',help='Only for synthetic tests, never scientific original')
    p.add_argument('--effective-prior-grid',type=Path,help='X-PSI-derived full M,R marginal prior; must be source-audited')
    p.add_argument('--rotating-eos-dir',type=Path,help='CSV files with mass_msun,radius_eq_km from validated rotating-star solver')
    p.add_argument('--prior-audit-file',type=Path,help='JSON signed provenance: status=VERIFIED, includes nuisance integration')
    p.add_argument('--rotation-audit-file',type=Path,help='JSON signed provenance: status=VERIFIED and spin_hz=346.536369')
    args=p.parse_args()
    res=preflight(args.posterior,check_sha=not args.allow_other_sha)
    gates=[('effective-prior-grid',args.effective_prior_grid),('rotating-eos-dir',args.rotating_eos_dir),('prior-audit-file',args.prior_audit_file),('rotation-audit-file',args.rotation_audit_file)]
    missing=[k for k,v in gates if v is None]
    if args.allow_other_sha:missing.append('source-integrity: --allow-other-sha forbids scientific EOS inference')
    if not missing:
        for k, f in [('prior',args.prior_audit_file),('rotation',args.rotation_audit_file)]:
            a=json.loads(f.read_text(encoding='utf-8'))
            if a.get('status')!='VERIFIED' or a.get('source') is None:
                missing.append(k+'-provenance-not-verified')
            if k=='prior' and not a.get('all_nuisance_marginalized',False): missing.append('full-nuisance-prior-not-marginalized')
            if k=='rotation' and not np.isclose(a.get('spin_hz',-1),346.536369,atol=1e-5):missing.append('rotation-frequency-mismatch')
    res['method']='joint posterior / full X-PSI marginal prior; one target radio mass prior; EOS R_eq(M,f)'
    res['group_combination']='alternative, separately normalized analysis posteriors may be mixed; never multiply groups'
    res['gates_missing']=missing
    if not missing:
        m,r=load_posterior(args.posterior, EXPECTED_SHA256)
        mg,rg,q=posterior_grid(m,r)
        pm,pr,pi=load_prior_grid(args.effective_prior_grid)
        if (len(pm)!=len(mg) or len(pr)!=len(rg) or not np.allclose(pm,mg) or not np.allclose(pr,rg)):
            raise ValueError('Prior grid must match posterior grid: reproduce exact axes, no interpolation shortcut')
        curves=sorted(args.rotating_eos_dir.glob('*.csv'))
        if not curves:raise ValueError('Missing rotating EOS CSVs')
        evidence=[];names=[]
        for f in curves:
            v=np.genfromtxt(f,delimiter=',',names=True)
            if not {'mass_msun','radius_eq_km'}.issubset(set(v.dtype.names or ())):
                raise ValueError('Invalid EOS curve '+str(f))
            evidence.append(integrate_eos_curve(mg,rg,q,pi,v['mass_msun'],v['radius_eq_km']))
            names.append(f.stem)
        res['eos_inference_status']='COMPUTED_CONDITIONAL_ON_AUDITED_INPUTS'
        res['eos_results']={n:{'log_relative_evidence':(float(z) if np.isfinite(z) else None),'within_group_posterior_weight':float(w)} for n,z,w in zip(names,evidence,normalized_weights(evidence))}
    else:
        res['eos_inference_status']='NOT_RUN: missing independent scientific inputs; cannot claim posterior'
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'preflight':res['preflight'],'eos_inference_status':res['eos_inference_status'],'gates_missing':missing},ensure_ascii=False))
    return 0



def integrate_eos_branches(m_grid, r_grid, q_grid, prior_grid,
                           branches, branch_prior=None, target_mass_pdf=None):
    """Compute EOS conditional log-score over *explicitly weighted* stable branches.

    Branch weights describe the astrophysical choice of stable branch at this
    fixed EOS, and are NOT inferred here. They must be supplied externally and
    must sum to one. Summing branch evidences without a normalized branch prior
    would silently double-count the same target-mass probability.

    This does not replace a source-native central-density population integral.
    """
    b = list(branches)
    if not b: raise ValueError('No stable EOS branches provided')
    if branch_prior is None:
        raise ValueError('branch_prior is required; no implicit equal weights or branch duplication')
    weights = np.asarray(branch_prior, dtype=float)
    if (weights.ndim != 1 or weights.size != len(b) or not np.all(np.isfinite(weights))
            or np.any(weights < 0) or not np.isclose(weights.sum(), 1., rtol=1e-10, atol=1e-10)):
        raise ValueError('branch_prior must have a finite nonnegative probability per branch and sum to one')
    parts=[]
    for (m,r),weight in zip(b,weights):
        if weight == 0: continue
        z=integrate_eos_curve(m_grid,r_grid,q_grid,prior_grid,m,r,
                              target_mass_pdf=target_mass_pdf)
        if np.isfinite(z): parts.append(np.log(weight)+z)
    if not parts: return -np.inf
    return float(logsumexp(parts))

if __name__=='__main__':sys.exit(main())
