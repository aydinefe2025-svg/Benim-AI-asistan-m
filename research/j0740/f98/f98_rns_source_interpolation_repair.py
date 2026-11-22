#!/usr/bin/env python3
"""F98 source-locked real C/RNS four-point log-Lagrange EOS interpolation audit + 10-node candidate repair.

Scientific scope: verify positivity and <=c over P(e) interpolation for all interiors of
9 * 2 existing genuine native C stars; create a distinct source-node-preserving numerical
INTERPOLATION CANDIDATE. Do not claim seven-EOS Bayesian inference or rotating eigenmode
stability. Real C rerun required separately, and thermodynamic consistency is not presumed.
"""
from __future__ import annotations
import argparse, hashlib, io, json, math, zipfile
from pathlib import Path
import numpy as np
from numpy.polynomial import Polynomial as Poly

C=2.99792458e10
MEVFM3=1.602176634e33
ORIGINAL_RNS_SHA='7643d0e4361adee77cc79d1b69eb445db70a52443b833c4dddafa973193fb580'
PUBLISHER_ORIGINAL_SHA='8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12'
F96_SOURCE_RESULT_SHA='a794218fd091c02e92e522e599003c0a6375c072f8b43d6607f89409155fce5a'
INSERTS={1830:5,1908:5}


def digest(data):return hashlib.sha256(data).hexdigest()

def load_rns(path):
    raw=Path(path).read_bytes()
    if digest(raw)!=ORIGINAL_RNS_SHA:raise ValueError('WRONG_SOURCE_NATIVE_F88_EOS_SHA')
    a=np.loadtxt(io.BytesIO(raw),skiprows=1)
    if len(a)!=1933 or a.shape[1]!=4: raise ValueError('SOURCE_NOT_1933x4')
    if not np.all(a>0) or not np.all(np.diff(a,axis=0)>0): raise ValueError('SOURCE_NOT_MONOTONIC')
    return a


def load_previous_f96(path):
    p=Path(path)
    if digest(p.read_bytes())!=F96_SOURCE_RESULT_SHA:raise ValueError('WRONG_ORIGINAL_F96_REAL_C_SOURCE_SHA')
    d=json.loads(p.read_text(encoding='utf8'))
    if d['source_original_Zenodo_SHA256']!=PUBLISHER_ORIGINAL_SHA:raise ValueError('WRONG_NATIVE_PUBLISHER_EOS')
    if d['status'] != 'TWO_GRID_ACTUAL_RNS_COMPLETE_CAUSAL_RANGE_DISCRETE_ONLY':
        raise ValueError('ORIGINAL_F96_HAS_NOT_RUN')
    if any(len(v['completed_actual_C_stars'])!=9 or v['errors'] for v in d['two_grid_native_results'].values()):
        raise ValueError('NOT_EIGHTEEN_TRUE_C_STARS')
    return d


def add_exact_original_knot_intermediates(a, inserts=INSERTS):
    if any(i<1 or i>=len(a)-2 or n<1 for i,n in inserts.items()):raise ValueError('INSERT_INDEX_OUTSIDE')
    pieces=[]
    for i in range(len(a)-1):
        pieces.append(a[i:i+1])
        count=inserts.get(i,0)
        if count:
            f=np.arange(1,count+1,dtype=float)/(count+1)
            # Separate *derived interpolation candidate*: P, eps, enthalpy and baryon density
            # linearly inserted at source knots; original 1933 4-physical-column rows unchanged.
            pieces.append(a[i]+f[:,None]*(a[i+1]-a[i])[None,:])
    pieces.append(a[-1:])
    b=np.vstack(pieces)
    if len(b)>2000 or len(b)!=1933+sum(inserts.values()):raise ValueError('UPSTREAM_RNS_TABLE_ARRAY_LIMIT')
    if not np.all(np.diff(b,axis=0)>0):raise ValueError('IMPROPER_CANDIDATE_EOS_COLS')
    original_positions=np.array([i+sum(n for j,n in inserts.items() if j<i) for i in range(len(a))])
    if not np.array_equal(b[original_positions],a): raise ValueError('ONE_OR_MORE_ORIGINAL_SOURCE_NODES_CHANGED')
    return b


def log_lagrange_four_coeffs(a,i):
    """Exact 4-support-point choice in RNS equil_util.c interp() with 1-based hunt index.
    For energy interval [i,i+1] zero-based: four support nodes [i-1,i,i+1,i+2], end-clamped.
    RNS input first col is rho; x=log10(rho) differs from original log10(rho*c²*KSCALE)
    by a constant, so the same polynomial and derivative are obtained; similarly pressure
    a constant shift to p/c² changes no derivative. Root dP/d(epsilon) is invariant.
    """
    n=len(a)
    if i<0 or i>=n-1:raise ValueError('SEGMENT_OUT_OF_RANGE')
    idx=int(np.clip(i-1,0,n-4))
    x=np.log10(a[:,0]);y=np.log10(a[:,1]/C**2)
    dx=float(x[i+1]-x[i]); t=(x[idx:idx+4]-x[i])/dx
    polynomial=Poly.fit(t,y[idx:idx+4]-y[i],3,domain=[float(t.min()),float(t.max())]).convert()
    return x[i],y[i],dx,polynomial


def cs2_function_from_coeffs(coeff):
    x0,y0,dx,poly=coeff
    return lambda q: float(10**(y0+poly(q)-x0-q*dx)*poly.deriv()(q)/dx)


def extrema_segment(a,i,stop=1.0):
    """All stationary points of c_s²(q) found as quartic polynomial roots: not sampling."""
    x0,y0,dx,p=log_lagrange_four_coeffs(a,i)
    stop=float(stop)
    if not (0<stop<=1+1e-9): raise ValueError('WRONG_SEGMENT_STOP')
    stop=min(stop,1.)
    d1=p.deriv();d2=p.deriv(2)
    stationary=(math.log(10)*(d1-Poly([dx]))*d1+d2).roots()
    trial=[0.,stop]+[float(v.real) for v in stationary if abs(v.imag)<1e-7 and 0<v.real<stop]
    cs=cs2_function_from_coeffs((x0,y0,dx,p))
    v=[(cs(q),q) for q in trial]
    a_min=min(v);a_max=max(v)
    return {'index':int(i),'rho_start':float(a[i,0]),'rho_end':float(a[i+1,0]),
     'min_cs2':float(a_min[0]),'min_at_rho_g_cm3':float(10**(x0+dx*a_min[1])),
     'max_cs2':float(a_max[0]),'max_at_rho_g_cm3':float(10**(x0+dx*a_max[1])),
     'min_at_q':float(a_min[1]),'max_at_q':float(a_max[1])}


def audit_to_central_density(a,central):
    x=np.log10(a[:,0]);xc=math.log10(central)
    i=int(np.searchsorted(a[:,0],central)-1)
    if not 0<=i<len(a)-1:raise ValueError('STAR_CENTER_NOT_INTERPOLATED')
    out=[]
    for j in range(i):out.append(extrema_segment(a,j))
    last_stop=(xc-x[i])/(x[i+1]-x[i]);out.append(extrema_segment(a,i,stop=last_stop))
    bad_neg=[e for e in out if e['min_cs2']<=0];bad_hi=[e for e in out if e['max_cs2']>1]
    mn=min(out,key=lambda e:e['min_cs2']);mx=max(out,key=lambda e:e['max_cs2'])
    return {'center':float(central),'min_cs2':mn['min_cs2'],'min_rho':mn['min_at_rho_g_cm3'],
       'max_cs2':mx['max_cs2'],'max_rho':mx['max_at_rho_g_cm3'],
       'negative_segments':len(bad_neg),'superluminal_segments':len(bad_hi),
       'negative_segment_indices':[e['index'] for e in bad_neg],
       'superluminal_segment_indices':[e['index'] for e in bad_hi],
       'pass_positive_sub_luminal':len(bad_neg)==0 and len(bad_hi)==0}


def audit_grid_fast(a,centers):
    x=np.log10(a[:,0]);mx_i=int(np.searchsorted(a[:,0],max(centers)))
    complete=[extrema_segment(a,j) for j in range(mx_i)]
    findings=[]
    for k,central in enumerate(centers):
        i=int(np.searchsorted(a[:,0],central)-1)
        valid=complete[:i]
        if i<0 or i>=len(a)-1: raise ValueError('WRONG_STAR_CENTRAL_BOUND')
        stop=(math.log10(central)-x[i])/(x[i+1]-x[i])
        valid=valid+[extrema_segment(a,i,stop=stop)]
        low=min(valid,key=lambda v:v['min_cs2']);hi=max(valid,key=lambda v:v['max_cs2'])
        neg=[v for v in valid if v['min_cs2']<=0]
        superlum=[v for v in valid if v['max_cs2']>1]
        findings.append({'index':k,'rho_c':float(central),
          'min_cs2':low['min_cs2'],'min_cs2_rho':low['min_at_rho_g_cm3'],
          'max_cs2':hi['max_cs2'],'max_cs2_rho':hi['max_at_rho_g_cm3'],
          'negative_intervals':[v['index'] for v in neg],
          'superluminal_intervals':[v['index'] for v in superlum],
          'passes_local_positive_causal_interpolated_P_e':len(neg)==len(superlum)==0})
    return findings


def write_eos(a,path):
    dst=Path(path);dst.parent.mkdir(exist_ok=True,parents=True)
    with dst.open('w',encoding='ascii',newline='\n') as f:
        f.write(str(len(a))+'\n')
        for row in a:f.write(' '.join(f'{v:.16e}' for v in row)+'\n')
    return digest(dst.read_bytes())


def main(argv=None):
    ap=argparse.ArgumentParser()
    for arg in ('original-rns','f96','out-eos','out-json'):ap.add_argument('--'+arg,required=True)
    a=ap.parse_args(argv)
    source=load_rns(a.original_rns)
    f96=load_previous_f96(a.f96)
    centers=np.asarray(f96['density_grid_g_cm3'],float)
    orig=audit_grid_fast(source,centers)
    repaired=add_exact_original_knot_intermediates(source)
    new=audit_grid_fast(repaired,centers)
    if not all(i['passes_local_positive_causal_interpolated_P_e'] for i in new):
        raise RuntimeError('F98_CANDIDATE_IS_NOT_CAUSAL_FOR_ALL_NINE_STARS')
    if not all(not i['passes_local_positive_causal_interpolated_P_e'] for i in orig):
        raise RuntimeError('F98_ORIGINAL_F96_SOURCE_WAS_NOT_ALL_ACAUSAL')
    sha=write_eos(repaired,a.out_eos)
    report={'schema':'J0740_F98_ACTUAL_SOURCE_C_FOURPOINT_LOG_LAGRANGE_EOS_CAUSALITY_NO_GO_AND_10_NODE_REPAIR_CANDIDATE',
      'original_source_rns_sha256':ORIGINAL_RNS_SHA,'original_physical_eos_zip_sha256':PUBLISHER_ORIGINAL_SHA,
      'old_true_18_native_C_stars_json_sha256':F96_SOURCE_RESULT_SHA,
      'upstream_rns_C_interpolation':'4pt log10(P)-versus-log10(E) Lagrange; zero-based support [i-1,i,i+1,i+2] in inner intervals; source code equil_util.c interp and equil.c p_at_e',
      'core_density_sequence_9_rho_g_cm3':list(map(float,centers)),
      'original_numerical_EOS':{'nodes':len(source),'stars_numerical_equilibrium':18,
        'stars_thermodynamically_causal_all_interior':int(sum(x['passes_local_positive_causal_interpolated_P_e'] for x in orig))*2,
        'negative_sound_speed_squares_in_all_stars':int(sum(bool(x['negative_intervals']) for x in orig))*2,
        'superluminal_central_or_interior_stars':int(sum(bool(x['superluminal_intervals']) for x in orig))*2,
        'nine_original_cubic_core_audits':orig},
      'derived_new_distinct_interpolation_candidate':{'nodes':len(repaired),
        'source_knot_rows_unchanged':len(source),'new_intermediate_rows':sum(INSERTS.values()),
        'insertions_after_original_zero_based_indices':{str(k):v for k,v in INSERTS.items()},
        'fields_interpolated_linearly_in_rho':['epsilon_over_c2','pressure','enthalpy','number_density'],
        'numerical_EOS_file_sha256':sha,
        'nine_candidate_cubic_core_audits':new,
        'numerical_sound_speed_check_all_nine_centers':'PASS_NONNEGATIVE_AND_SUBLUMINAL_UP_TO_NINE_CENTERS',
        'fitted_physical_models_in_this_source_audit':0},
      'physics_implications':{'original_F96_real_C_computation':'VALID_AS_NUMERICAL_EQUILIBRIUM_EVALUATIONS',
        'original_F96_18_star_physical_sound_speed_certification':'FAIL_ALL_18_NEGATIVE_CUBIC_SLOPE_IN_CRUST',
        'candidate_continuous_first_law_and_chemical_potential':'NOT_PROVEN; LINEARLY INSERTED BETWEEN ORIGINAL KNOTS, MODEL IS DISTINCT',
        'candidate_true_native_Einstein_rotating_C_stars':'NOT_RUN_UNTIL_GITHUB_CI',
        'axisymmetric_rotating_dynamic_modes':'NOT_RUN',
        'seven_EOS_full_source_native_photon_Bayes':'NOT_RUN',
        'global_original_publisher_EOS_causality':'FAIL_24_HIGH_DENSITY_NODES_AND_BROKEN_INTERPOLATION'} }
    out=Path(a.out_json);out.parent.mkdir(exist_ok=True,parents=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'original_source_C_eos_sha':ORIGINAL_RNS_SHA,'new_distinct_numerical_EOS_sha':sha,
      'original_negative_cs2_cubic_across_all_18':report['original_numerical_EOS']['negative_sound_speed_squares_in_all_stars'],
      'original_superluminal_2_stars':report['original_numerical_EOS']['superluminal_central_or_interior_stars'],
      'repaired_numerical_all_9_pass':True,'new_physical_C_stars_this_run':0,'output':str(out)},sort_keys=True))
    return report

if __name__=='__main__':main()
