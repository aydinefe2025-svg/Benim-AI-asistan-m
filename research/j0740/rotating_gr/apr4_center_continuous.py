"""Pinned APR4 source PCHIP *interpolant* screen up to J0740 RNS centre.

This is a new mathematical between-knot numerical check, NOT a certification of
LALSuite's native EOS, the surface crust, baryon conservation, or star physics.
Original NPZ arrays are read-only and hash verified.
"""
from __future__ import annotations
import hashlib
import math
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

G_SI = 6.67430e-11
C_SI = 299792458.0

class SourceInvalid(ValueError):
    pass


def exact_interval_bounds(c, h, x_left):
    """Extrema of cs²/c²=exp(x-y(x))/y'(x), where y=log(e), x=log(p).

    Cubic PCHIP y(z)=A z³+B z²+C z+D, z=(x-x_left)/h in [0,1].
    s=dy/dx is quadratic. Stationary cs² solves s*(1-s)-ds/dx=0,
    quartic in z. Checks endpoints, all real interior roots, and slope vertex.
    """
    c=np.asarray(c,float)
    if c.shape!=(4,) or not np.isfinite(c).all() or not (math.isfinite(h) and h>0):
        raise ValueError('Invalid PCHIP interval')
    A,B,C,D=float(c[0]*h**3),float(c[1]*h**2),float(c[2]*h),float(c[3])
    y=lambda z: ((A*z+B)*z+C)*z+D
    s=lambda z:(3*A*z*z+2*B*z+C)/h
    vertex=-B/(3*A) if abs(A)>1e-30 else float('nan')
    slope_candidates=[0.0,1.0]
    if 0<vertex<1:slope_candidates.append(vertex)
    min_s=min(s(z) for z in slope_candidates)
    if min_s<=0 or not math.isfinite(min_s):
        return {'derivative_min':min_s,'cs2_min':None,'cs2_max':None,'positive':False,'n_stationary_roots':None}
    # polynomial ascending in z
    s_poly=np.array([C,2*B,3*A],float)/h
    sp_poly=np.array([2*B,6*A],float)/(h*h)
    q=np.polynomial.polynomial.polysub(s_poly,np.polynomial.polynomial.polymul(s_poly,s_poly))
    q=np.polynomial.polynomial.polysub(q,sp_poly)
    while len(q)>1 and abs(q[-1])<1e-14*float(np.max(np.abs(q))):q=q[:-1]
    stations=[]
    if len(q)>1:
        for root in np.polynomial.polynomial.polyroots(q):
            if abs(root.imag)<1e-8 and 0<root.real<1:
                stations.append(float(root.real))
    cand=[0.0,1.0]+stations
    cs=[math.exp(x_left+h*z-y(z))/s(z) for z in cand]
    return {'derivative_min':float(min_s),'cs2_min':float(min(cs)),
            'cs2_max':float(max(cs)),'positive':True,'n_stationary_roots':len(stations)}


def audit_continuous(p,e,cs2,center_e):
    p,e,cs2=(np.asarray(t,float) for t in (p,e,cs2))
    if any(v.ndim!=1 or len(v)<5 for v in (p,e,cs2)) or not(p.shape==e.shape==cs2.shape):
        raise SourceInvalid('Invalid source arrays')
    if not all(np.isfinite(t).all() for t in (p,e,cs2)) or not math.isfinite(float(center_e)):
        raise SourceInvalid('Nonfinite source')
    if np.any(p<=0) or np.any(e<=0) or np.any(np.diff(p)<=0):
        raise SourceInvalid('Pressure or source energy invalid')
    if np.any(np.diff(e)<=0):
        raise SourceInvalid('Source energy nonmonotonic: refuse physical candidate')
    if not e[0]<center_e<e[-1]:
        raise SourceInvalid('RNS stellar centre outside source energy range')
    x=np.log(p); y=np.log(e)
    spline=PchipInterpolator(x,y,extrapolate=False)
    xc=float(brentq(lambda a:float(spline(a)-math.log(center_e)),float(x[0]),float(x[-1]),xtol=1e-14))
    pcenter=float(math.exp(xc))
    bounded=[];first_bad=None; all_dense_agree=True
    for i in range(len(p)-1):
        xlo=float(x[i]);hi=min(float(x[i+1]),xc)-xlo
        if hi<=1e-13:break
        b=exact_interval_bounds(spline.c[:,i],hi,xlo)
        bad=(not b['positive'] or b['cs2_max']>1+1e-11)
        if bad and first_bad is None:first_bad=i
        # A separate dense interpolation check cannot certify, but can falsify bounds.
        sample=np.linspace(xlo,xlo+hi,61)
        v=np.exp(sample-spline(sample))/spline.derivative()(sample)
        if b['positive']:
            if not np.all(np.isfinite(v)) or np.any(v>b['cs2_max']*(1+3e-8)) or np.any(v<b['cs2_min']*(1-3e-8)):
                all_dense_agree=False
        bounded.append(b)
    if not bounded or not all_dense_agree:raise AssertionError('Continuous stationarity/root bounds mismatch dense falsification')
    min_c=min(b['cs2_min'] for b in bounded if b['positive']) if all(b['positive'] for b in bounded) else None
    max_c=max(b['cs2_max'] for b in bounded if b['positive']) if all(b['positive'] for b in bounded) else None
    in_star=e<=center_e
    native_min=float(cs2[in_star].min());native_max=float(cs2[in_star].max())
    pass_c=(all(b['positive'] and b['cs2_max']<=1 for b in bounded)
             and native_min>0 and native_max<=1)
    over_idx=np.flatnonzero(cs2>1)
    return {'interpolant_status':'PASS_CANDIDATE_BETWEEN_KNOT_SCREEN' if pass_c else 'FAIL_CANDIDATE_CAUSALITY',
       'source_nodes':len(p),'source_center_energy_geom':float(center_e),
       'p_center':pcenter,'intervals_reaching_center':len(bounded),
       'pchip_center_truncated_cs2_min':min_c,'pchip_center_truncated_cs2_max':max_c,
       'pchip_strict_positive_slopes_all_intervals':all(b['positive'] for b in bounded),
       'pchip_first_failed_interval':first_bad,
       'source_native_center_truncated_cs2_min':native_min,
       'source_native_center_truncated_cs2_max':native_max,
       'native_first_superluminal_node_index':int(over_idx[0]) if len(over_idx) else None,
       'native_first_superluminal_node_energy_over_center':float(e[over_idx[0]]/center_e) if len(over_idx) else None,
       'independent_dense_falsification':'PASS_61_POINTS_PER_INTERVAL',
       'limitations':'PCHIP interpolation candidate only; not native LALSuite EOS proof; no P->0 crust; no thermodynamic n(P) or RNS new solver.'}


def audit_pinned_npz(path, fixture):
    path=Path(path)
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    if sha!=fixture['expected_source_sha256']:
        raise SourceInvalid('Pinned original EOS NPZ SHA-256 mismatch')
    with np.load(path,allow_pickle=False) as z:
        if not {'p','e','cs2'}.issubset(z.files):raise SourceInvalid('EOS NPZ missing required keys')
        p,e,cs2=z['p'],z['e'],z['cs2']
    if len(p)!=fixture['expected_source_rows']:raise SourceInvalid('EOS row-count mismatch')
    # rho_g/cm3 *1000 -> SI energy density epsilon/c2 [kg/m3] -> geometric eps [m-2]
    center_e=float(fixture['center_rho_g_cm3']*1000.*G_SI/C_SI**2)
    answer=audit_continuous(p,e,cs2,center_e)
    answer.update({'source_sha256':sha,'source_rows_pinned':fixture['expected_source_rows'],
                  'pinned_reference':'JESTER e6768650ce992abfd1153a6833857572fe5cd230; 7EOS GR run 42353019033'})
    return answer
