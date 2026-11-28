"""Thermodynamic first-law reconstruction for a *local hypothetical* EOS patch.

Only five fixed pressure samples 252:256; a piecewise-linear epsilon(P) between
neighboring points. n(P) is recovered from d ln n=d epsilon/(epsilon+P),
and pseudoenthalpy h(P) from dh=dP/(epsilon+P). No untested 7-EOS
stellar solution or complete EOS is implied. Original data are untouched.
"""
from __future__ import annotations
import math

class LocalThermoError(ValueError):
    """Input is noncausal, nonmonotone, inconsistent or outside the local scope."""


def integrate_segment(e0: float,p0: float,e1: float,p1: float,*,cap:float=.95)->dict:
    values=(e0,p0,e1,p1,cap)
    if not all(math.isfinite(v) for v in values) or not (e0>0 and p0>0 and e1>0 and p1>p0 and 0<cap<=1):
        raise LocalThermoError('Invalid or nonmonotonic positive pressure/energy input')
    de=e1-e0
    if de<=0:
        raise LocalThermoError('nonmonotonic e(P): cannot reconstruct stable single-valued EOS')
    dp=p1-p0
    cs2=dp/de
    if cs2>cap*(1+2e-12):
        raise LocalThermoError('noncausal sampled secant: c_s^2 exceeds declared cap')
    # a=d epsilon / dP; e(P)=e0+a(P-p0).
    a=de/dp
    delta_ln_ep=math.log1p((de+dp)/(e0+p0))
    delta_h=delta_ln_ep/(1+a)
    delta_ln_n=a*delta_h
    # Independently integrate dh/dP by Simpson's rule (512 subintervals).
    pieces=512
    step=dp/pieces
    terms=1/(e0+p0)+1/(e1+p1)
    for i in range(1,pieces):
        pi=p0+step*i
        ei=e0+de*i/pieces
        terms+=(4 if i%2 else 2)/(ei+pi)
    simpson=(step/3)*terms
    error=abs(delta_ln_ep-delta_h-delta_ln_n)
    return {'cs2_over_c2':cs2,'de_dp':a,
            'delta_h':delta_h,'delta_ln_n':delta_ln_n,
            'delta_h_simpson':simpson,
            'simpson_rel_error':abs(simpson-delta_h)/delta_h,
            'first_law_identity_abs_error':error}


def integrate_repaired_five_nodes(rows:list[dict],candidate_energies:list[float],*,cap:float=.95)->dict:
    if (len(rows)!=5 or len(candidate_energies)!=5 or
        [x.get('index') for x in rows]!=[252,253,254,255,256]):
        raise LocalThermoError('Five source rows 252:256 required')
    p=[float(x['p_geom_m_minus2']) for x in rows]
    e=[float(x) for x in candidate_energies]
    if not all(math.isfinite(v) and v>0 for v in p+e):
        raise LocalThermoError('Nonfinite candidate or pressure value')
    if any(y<=x for x,y in zip(p,p[1:])):
        raise LocalThermoError('nonmonotonic pressure')
    original=[float(x['energy_geom_m_minus2']) for x in rows]
    if any(e[i]!=original[i] for i in (0,3,4)):
        raise LocalThermoError('Fixed outer anchors 252/255/256 must be preserved')
    pieces=[integrate_segment(e[i],p[i],e[i+1],p[i+1],cap=cap) for i in range(4)]
    h0=float(rows[0]['h'])
    h=[h0]
    ln_n=[0.]
    for piece in pieces:
        h.append(h[-1]+piece['delta_h'])
        ln_n.append(ln_n[-1]+piece['delta_ln_n'])
    n=[math.exp(a) for a in ln_n]
    # Source JESTER uses approximate n(P)=epsilon(P)/m_avg, hence its normalized
    # baryon density would be simply epsilon_i/epsilon_252. For P>0 it does
    # not satisfy the cold-barotrope first law exactly.
    source_n_proxy_at_end=e[-1]/e[0]
    difference=abs(source_n_proxy_at_end/n[-1]-1)
    return {
        'status':'LOCAL_PIECEWISE_LINEAR_IDENTITY_PASS',
        'local_scope_source_indices':[252,253,254,255,256],
        'piecewise_cs2_over_c2':[x['cs2_over_c2'] for x in pieces],
        'candidate_pseudoenthalpy_h':h,
        'source_native_pseudoenthalpy_h':[float(x['h']) for x in rows],
        'max_abs_h_difference_from_source':max(abs(h[i]-float(rows[i]['h'])) for i in range(5)),
        'relative_baryon_density':n,
        'source_proxy_n_over_n252': [v/e[0] for v in e],
        'relative_difference_approx_n_vs_thermodynamic_n_at_256':difference,
        'max_first_law_identity_abs_error':max(x['first_law_identity_abs_error'] for x in pieces),
        'max_analytic_vs_simpson_relative_error':max(x['simpson_rel_error'] for x in pieces),
        'local_linear_segments_only':True,
        'physical_EOS_overall_validated':False,
        'rns_tov_computed':False,
        'native_lalsuite_cs2_changed':False,
    }
