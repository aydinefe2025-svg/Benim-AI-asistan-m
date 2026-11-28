"""Fail-closed, *sampled-source* EOS screen on pinned JESTER LALSuite NPZ tables.

Source-wide node/interval diagnostics and first-law discrepancy are *not*
a continuous analytic causal proof or a new physically repaired EOS.

No data download or stellar solver is invoked by this module.
"""
from __future__ import annotations

import math
import numpy as np

# An integration of the *source's log-linear representation*, deliberately
# separate from the native LALSuite analytic derivative. 32-node Legendre
# quadrature is independent of endpoint-secants and stable over log-P bins.
_QX, _QW = np.polynomial.legendre.leggauss(32)


def audit_arrays(p, e, n, h, cs2, *, center_e):
    """Screen table using original sampled LALSuite values, no editing.

    p,e in the same geometrized units; n positive baryon density values;
    h dimensionless pseudoenthalpy, cs2 native LALSuite derivative / c^2.
    ``center_e`` is the historical rotating-star energy density in e units.
    """
    a = [np.asarray(x, dtype=np.float64) for x in (p, e, n, h, cs2)]
    if any(v.ndim != 1 or len(v) < 4 for v in a):
        raise ValueError('Expected 5 one-dimensional native EOS arrays')
    if len({len(v) for v in a}) != 1:
        raise ValueError('Inconsistent native EOS array lengths')
    if not all(np.isfinite(v).all() for v in a) or not math.isfinite(float(center_e)):
        raise ValueError('Nonfinite native source EOS')
    p,e,n,h,cs2 = a
    if np.any(p <= 0) or np.any(e <= 0) or np.any(n <= 0) or center_e <= 0:
        raise ValueError('Physical densities/pressures must be positive')
    if np.any(np.diff(p) <= 0):
        raise ValueError('Pressure order must be strictly ascending')
    if np.any(np.diff(h) <= 0):
        raise ValueError('Source pseudoenthalpy not strictly ascending')
    if not p[0] < p[-1] or not e[0] < center_e < e[-1]:
        # A user should not count a fictional within-star center as a pass.
        raise ValueError('Rotating center must lie inside source energy range')

    dp=np.diff(p)
    de=np.diff(e)
    dcs=np.divide(dp,de,out=np.full_like(dp,np.inf),where=de != 0)
    below=(e<=center_e)
    in_star_edges=(e[:-1]<=center_e)&(e[1:]<=center_e)
    native_neg=(cs2<=0)&below
    native_over=(cs2>1)&below
    segment_invalid=(dcs<=0)|(~np.isfinite(dcs))
    segment_over=dcs>1*(1+2e-12)

    # Thermodynamic first-law expected log baryon-density increments under
    # log-linear epsilon(P) between *each pair* of source pressure samples.
    # dln(n)= d(epsilon)/(epsilon+P).
    dlnp=np.diff(np.log(p))
    alpha=np.diff(np.log(e))/dlnp
    fraction = .5 * dlnp[:,None] * (_QX[None,:]+1)
    ln_p_sample = np.log(p[:-1,None]) + fraction
    ln_e_sample = np.log(e[:-1,None]) + alpha[:,None] * fraction
    pp = np.exp(ln_p_sample)
    ee = np.exp(ln_e_sample)
    half_bin = .5*dlnp
    # d(epsilon)/(epsilon+P) = alpha * epsilon/(epsilon+P) dln(P)
    dln_n_firstlaw = half_bin * np.sum(_QW[None,:] * alpha[:,None] * ee/(ee+pp),axis=1)
    dln_n_source = np.diff(np.log(n))
    ln_n_error = np.cumsum(dln_n_source - dln_n_firstlaw)
    n_fraction_end = float(np.expm1(ln_n_error[-1]))

    # h(P) = integral dP/(epsilon+P) in geometrized units under same assumption.
    d_h = half_bin * np.sum(_QW[None,:] * pp/(ee+pp),axis=1)
    source_dh = np.diff(h)
    max_dh_fraction_error = float(np.max(np.abs(d_h-source_dh) / np.maximum(np.abs(source_dh),1e-16)))

    native_neg_count=int(native_neg.sum())
    native_over_count=int(native_over.sum())
    sec_neg=int(np.count_nonzero(segment_invalid&in_star_edges))
    sec_over=int(np.count_nonzero(segment_over&in_star_edges))
    sampled_pass = not (native_neg_count or native_over_count or sec_neg or sec_over)
    return {
        'sampled_source_screen':'SAMPLED_PASS_NOT_GLOBAL_PROOF' if sampled_pass else 'FAIL_IN_STAR',
        'N_source_nodes':int(len(e)),
        'rotating_center_energy_geom':float(center_e),
        'negative_native_cs2_below_center':native_neg_count,
        'superluminal_native_cs2_below_center':native_over_count,
        'negative_secants_below_center':sec_neg,
        'superluminal_secants_below_center':sec_over,
        'native_cs2_below_center_min':float(cs2[below].min()),
        'native_cs2_below_center_max':float(cs2[below].max()),
        'source_energy_nonincreasing_edges_global':int(np.count_nonzero(de<=0)),
        'source_n_nonincreasing_edges_global':int(np.count_nonzero(np.diff(n)<=0)),
        'native_cs2_superluminal_nodes_global':int(np.count_nonzero(cs2>1)),
        'native_cs2_nonpositive_nodes_global':int(np.count_nonzero(cs2<=0)),
        'native_cs2_max_global':float(cs2.max()),
        'firstlaw_n_normalized_terminal_fractional_mismatch':n_fraction_end,
        'firstlaw_n_normalized_max_abs_fractional_mismatch':float(np.max(np.abs(np.expm1(ln_n_error)))),
        'firstlaw_h_source_vs_loglinear_max_interval_relative_difference':max_dh_fraction_error,
        'native_n_over_e_min':float(np.min(n/e)),
        'native_n_over_e_max':float(np.max(n/e)),
        'max_pressure_e_fraction':float(np.max(p/e)),
        'caveat':'Finite JESTER nodes and log-linear intervals only; original LALSuite derivative may differ between nodes. No physical repairs, zero-P extrapolation, TOV, Love or RNS rerun.',
    }
