#!/usr/bin/env python3
"""F78 source-only seven EOS, 323 authentic GR RNS centre baryon-proxy diagnostic.

Source JESTER npz `n` is proportional to epsilon, which cannot obey the
zero-temperature first law at nonzero pressure. Compare its RELATIVE density
shape with a first-law shape implied by the original source (p,e,h) columns,
normalized at the source's first pressure knot. This is NOT calibrated baryon
number, NOT a physical EOS correction, and never changes original stars.
"""
from __future__ import annotations
import argparse, hashlib, io, json, sys
from pathlib import Path
import numpy as np

_HERE=Path(__file__).resolve().parent
if (_HERE.parent/'f75').is_dir():
    sys.path.insert(0,str(_HERE.parent/'f75'))
from f75_original_eos_causality_gate import EOS, load_original_stars, require_sha, GEOM_E_TO_G_CM3

MODEL='J0740_F78_SOURCE_N_IS_E_OVER_CONSTANT_NOT_BARYON_DENSITY_V1'


def firstlaw_shape_ratio(p,e,h,n,*,tolerance=1e-12):
    """n_proxy/n_H relative to p[0]. All n_H values carry ARBITRARY n0.

    n_H/n_H0 = [(e+p)/(e0+p0)] exp[-(h-h0)]; only first-law exact if h
    really integrates dP/(e+p). Original numerical low-P E(P) path may fail.
    """
    p,e,h,n=[np.asarray(a,dtype=np.float64) for a in (p,e,h,n)]
    if not (p.ndim==e.ndim==h.ndim==n.ndim==1 and len(p)>=100 and
            len(p)==len(e)==len(h)==len(n)):
        raise ValueError('source_array_shape_incorrect')
    if any(not np.isfinite(a).all() for a in (p,e,h,n)) or any(np.any(a<=0) for a in (p,e,n)):
        raise ValueError('source_nonpositive_or_nonfinite')
    if np.any(np.diff(p)<=0) or np.any(np.diff(h)<=0):
        raise ValueError('source_pressure_or_H_not_increasing')
    # Whether n is energy-density-derived is a measured source fact, never
    # imposed as input by the computation.
    reduced=n/e
    if np.max(np.abs(reduced/reduced[0]-1))>tolerance:
        raise ValueError('n_not_energy_density_proxy_source_changed')
    n_h_over_n0=(e+p)/(e[0]+p[0])*np.exp(-(h-h[0]))
    if np.any(~np.isfinite(n_h_over_n0)) or np.any(n_h_over_n0<=0):
        raise ValueError('inconsistent_enthalpy_reconstruction')
    n_proxy_over_n0=n/n[0]
    return {
        'n_over_e_source_scale':float(reduced[0]),
        'max_absolute_relative_n_over_e_residual':float(np.max(np.abs(reduced/reduced[0]-1))),
        'n_H_over_n0':n_h_over_n0,
        'n_proxy_over_n0':n_proxy_over_n0,
        'n_proxy_over_n_H':n_proxy_over_n0/n_h_over_n0,
        'n_H_nonincreasing_edges':int(np.count_nonzero(np.diff(n_h_over_n0)<=0)),
        'n_proxy_nonincreasing_edges':int(np.count_nonzero(np.diff(n)<=0)),
    }


def bracket_center(p,e,h,n,target_e):
    """Diagnostic log-e interpolation between *authentic adjacent source knots*.

    No extrapolation, no interpolation through two different branches, no
    claim this is the native LAL spline's exact pressure at e_c.
    """
    p,e,h,n=[np.asarray(a,dtype=np.float64) for a in (p,e,h,n)]
    target_e=float(target_e)
    if not np.isfinite(target_e) or target_e<=0:raise ValueError('invalid_center')
    # A target exactly on a source knot belongs to two adjacent brackets.
    # Give that unique physical source point a deterministic canonical bracket.
    exact=np.flatnonzero(e==target_e)
    if len(exact)==1:
        j=int(exact[0]);i=min(j,len(e)-2)
        if e[i+1]<=e[i]:
            i=j-1
        if i<0 or e[i+1]<=e[i]:raise ValueError('not_exactly_one_source_center_bracket')
    else:
        edges=np.flatnonzero((e[:-1]<target_e)&(target_e<e[1:])&(e[1:]>e[:-1]))
        if len(edges)!=1:raise ValueError('not_exactly_one_source_center_bracket')
        i=int(edges[0])
    t=(np.log(target_e)-np.log(e[i]))/(np.log(e[i+1])-np.log(e[i]))
    if not (0<=t<=1):raise ValueError('bracket_numerical_fault')
    pp=float(np.exp(np.log(p[i])*(1-t)+np.log(p[i+1])*t))
    hh=float(h[i]*(1-t)+h[i+1]*t)
    # Native n is epsilon proxy across exact knots; interpolate using its
    # exact measured relation rather than treating it as independent baryons.
    nn=float(n[0]*target_e/e[0]);
    ratio=((nn/n[0])/((target_e+pp)/(e[0]+p[0])*np.exp(-(hh-h[0]))))
    return {'lower_source_knot':i,'upper_source_knot':i+1,
            'log_e_interpolation_weight':float(t),
            'central_pressure_geom_m-2_DIAGNOSTIC':pp,
            'central_native_H_DIAGNOSTIC':hh,
            'n_proxy_over_normalized_n_H_DIAGNOSTIC':float(ratio),
            'n_H_over_proxy_DIAGNOSTIC':float(1/ratio),
            'loglinear_pressure_not_native_LAL_spline':True}


def analyze(source_dir,artifacts_dir,source_manifest,artifact_manifest):
    sf=json.loads(Path(source_manifest).read_text())
    af=json.loads(Path(artifact_manifest).read_text())
    if sf['pinned_commit']!=af['original_JESTER_commit'] or set(sf['records'])!=set(EOS):
        raise ValueError('wrong_JESTER_source_manifest')
    out={'schema':MODEL,'JESTER_commit':sf['pinned_commit'],
         'original_RNS_commit':af['original_RNS_commit'],
         'reference_anchor':'first original positive pressure EOS knot, n_H0 = n_proxy0 (ARBITRARY, NOT physical chemical potential)',
         'exact_no_go':'If n_proxy=epsilon/k at P>0, d epsilon=(epsilon+P) d n/n requires P=0; thus this n column cannot be independent cold first-law baryon number density.',
         'method':'Use original JESTER p,e,h,n arrays and authentic stored C centres, no new EOS or stars; inverse e->P/H using ONLY two adjacent source knots, log-e diagnostic.',
         'source_n_is_not_thermodynamic_baryon_density':True,
         'absolute_baryon_number_or_mass':'NOT_CALIBRATED',
         'new_rotating_RNS':'NOT_RUN',
         'source_native_XPSI_photon_likelihood':'NOT_RUN',
         'source_native_physical_EOS_certification':'NOT_ESTABLISHED',
         'EOS_Bayes':'NOT_RUN',
         'number_real_stars':0,'models':{}}
    for name in EOS:
        blob=(Path(source_dir)/(name+'.npz')).read_bytes();require_sha(blob,sf['records'][name]['sha256'],'JESTER_'+name)
        a=np.load(io.BytesIO(blob),allow_pickle=False)
        if str(a['eos_name'])!=name or str(a['source'])!='LALSimulation':raise ValueError('EOS_source_identity')
        p,e,h,n=[a[k] for k in ('p','e','h','n')]
        sh=firstlaw_shape_ratio(p,e,h,n)
        stars,orig=load_original_stars(Path(artifacts_dir),af,name)
        if orig['source_original_npz_sha256']!=sf['records'][name]['sha256']:raise ValueError('EOS_RNS_source_mismatch')
        cs=[]
        for i,star in enumerate(stars):
            if abs(star['spin_residual_hz'])>star['allowed_spin_residual_hz']+1e-9:
                raise ValueError('authentic_star_spin_tolerance_violated')
            ec=star['central_energy_density_g_cm3']/GEOM_E_TO_G_CM3
            diag=bracket_center(p,e,h,n,ec)
            cs.append({'original_C_star_index':i,'mass_msun':float(star['mass_msun']),
                       'central_energy_density_g_cm3':float(star['central_energy_density_g_cm3']),**diag})
        rr=np.array([x['n_proxy_over_normalized_n_H_DIAGNOSTIC'] for x in cs])
        out['models'][name]={
          'original_npz_sha256':sf['records'][name]['sha256'],
          'original_RNS_JSON_sha256':af['artifacts'][name]['json_sha256'],
          'n_knots':len(e),'n_over_e_source_scale':sh['n_over_e_source_scale'],
          'max_n_over_e_relative_residual':sh['max_absolute_relative_n_over_e_residual'],
          'pressure_positive_all_knots':bool(np.all(p>0)),
          'source_H_strictly_increasing':bool(np.all(np.diff(h)>0)),
          'n_H_monotonicity_bad_edges':sh['n_H_nonincreasing_edges'],
          'original_source_proxy_n_bad_edges':sh['n_proxy_nonincreasing_edges'],
          'highest_source_knot_n_proxy_over_n_H':float(sh['n_proxy_over_n_H'][-1]),
          'highest_source_knot_H_normalized_n_H_over_proxy':float(1/sh['n_proxy_over_n_H'][-1]),
          'original_RNS_C_stars':len(cs),
          'C_center_proxy_over_n_H_min':float(rr.min()),
          'C_center_proxy_over_n_H_median':float(np.median(rr)),
          'C_center_proxy_over_n_H_max':float(rr.max()),
          'C_center_proxy_over_n_H_at_mass_nearest_2p073':float(min(cs,key=lambda x:abs(x['mass_msun']-2.073))['n_proxy_over_normalized_n_H_DIAGNOSTIC']),
          'original_C_centers':cs,
          'physical_baryon_mass':'NOT_INFERRED',
          'numerical_source_lowP_broken_edges_preclude_whole_EOS_firstlaw':'NOT_PHYSICALLY_REPAIRED'}
        out['number_real_stars']+=len(cs)
    if out['number_real_stars']!=323:raise ValueError('star_count_not_323')
    return out


def main():
    ap=argparse.ArgumentParser()
    for x in ('source-dir','artifacts-dir','source-manifest','artifact-manifest','out'):
        ap.add_argument('--'+x,type=Path,required=True)
    args=ap.parse_args()
    result=analyze(args.source_dir,args.artifacts_dir,args.source_manifest,args.artifact_manifest)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n')
    print('F78 authentic stars',result['number_real_stars'])
    for k,v in result['models'].items():print(k,'mean proxy/H median ratio',v['C_center_proxy_over_n_H_median'], 'near_2.073',v['C_center_proxy_over_n_H_at_mass_nearest_2p073'])
    print('F78 NOT physical baryon mass, not source native photons')
if __name__=='__main__':main()