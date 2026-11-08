"""Independent shape-preserving EOS interpolation *candidate* audit.

Verifies full continuous log(e) vs log(p) derivative and c_s^2 extrema for
PCHIP, not LALSimulation's original cubic EOS and not Codex's Steffen candidate.
Uses pinned, unaltered JESTER source; cannot establish a physical P->0 crust,
correct native EOS sound speed, a rotating RNS sequence or Bayes evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator

EOS = ("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")
PINNED_JESTER = "e6768650ce992abfd1153a6833857572fe5cd230"
PINNED_RNS_JSON_SHA256 = "d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"


def extrema_on_interval(c: np.ndarray, h: float, x_left: float) -> dict:
    """Exact polynomial candidates, not a finite mesh, on x_left<=x<=x_left+h.

    PchipInterpolator.c columns are y(x_left+t) = c0*t^3+c1*t^2+c2*t+c3.
    dy/dx is quadratic; c_s^2 = exp(x-y(x)) / (dy/dx). Its stationary
    locations satisfy s*(1-s)-s' = 0, a polynomial of at most degree four.
    """
    if c.shape != (4,) or not np.all(np.isfinite(c)) or not math.isfinite(h) or h <= 0:
        raise ValueError("Invalid cubic interval")
    a, b, d, e0 = [float(v) for v in c]
    # Evaluate in scaled z=t/h in [0,1] for conditioned root solving.
    A, B, C = a*h**3, b*h**2, d*h
    y = lambda z: ((A*z + B)*z + C)*z + e0
    slope = lambda z: (3*A*z*z + 2*B*z + C)/h
    vertex = (-B/(3*A) if abs(A)>1e-30 else float("nan"))
    deriv_candidates = [0.0, 1.0]
    if 0 < vertex < 1:
        deriv_candidates.append(vertex)
    s_vals=[slope(z) for z in deriv_candidates]
    min_s=float(min(s_vals)); max_s=float(max(s_vals))
    # Quartic stationary equation: (s-s*s)-ds/dx == 0.
    # s(z) coefficients in ascending order.
    s=np.array([C, 2*B, 3*A],dtype=float)/h
    sp=np.array([2*B,6*A],dtype=float)/(h*h)
    poly = np.polynomial.polynomial.polysub(
        s, np.polynomial.polynomial.polymul(s,s))
    poly = np.polynomial.polynomial.polysub(poly,sp)
    while len(poly)>1 and abs(poly[-1]) < 1e-13*max(1.0,float(np.max(np.abs(poly)))):
        poly=poly[:-1]
    candidates=[0.0,1.0]
    if len(poly)>1:
        roots=np.polynomial.polynomial.polyroots(poly)
        for root in roots:
            if abs(root.imag)<1e-8 and -1e-9 <= root.real <=1+1e-9:
                candidates.append(float(np.clip(root.real,0.0,1.0)))
    if min_s <= 0:
        return {"derivative_min":min_s,"derivative_max":max_s,
                "cs2_min":None,"cs2_max":None,"is_strictly_stable":False,
                "stationary_candidates":len(candidates)}
    vals=[math.exp(x_left+h*z-y(z))/slope(z) for z in candidates]
    return {"derivative_min":min_s,"derivative_max":max_s,
            "cs2_min":float(min(vals)),"cs2_max":float(max(vals)),
            "is_strictly_stable":True,"stationary_candidates":len(candidates)}


def audit_arrays(p:np.ndarray,e:np.ndarray,source_cs2:np.ndarray) -> dict:
    p,e,source_cs2=(np.asarray(z,dtype=float) for z in (p,e,source_cs2))
    if (p.ndim!=1 or p.size<4 or p.shape!=e.shape or e.shape!=source_cs2.shape
        or not all(np.all(np.isfinite(z)) for z in (p,e,source_cs2))
        or np.any(p<=0) or np.any(e<=0) or np.any(np.diff(p)<=0)):
        raise ValueError("Source data invalid or pressure nonmonotonic")
    if np.any(np.diff(e)<=0):
        raise ValueError("Original energy-density nodes not strictly monotonic; refuse a physical repair")
    x=np.log(p); y=np.log(e)
    pp=PchipInterpolator(x,y,extrapolate=False)
    intervals=[extrema_on_interval(pp.c[:,i],float(x[i+1]-x[i]),float(x[i]))
               for i in range(len(x)-1)]
    stable=all(d['is_strictly_stable'] for d in intervals)
    min_derivative=min(t['derivative_min'] for t in intervals)
    max_derivative=max(t['derivative_max'] for t in intervals)
    cs2_max=max((q['cs2_max'] for q in intervals if q['cs2_max'] is not None),default=None)
    cs2_min=min((q['cs2_min'] for q in intervals if q['cs2_min'] is not None),default=None)
    first_bad=[i for i,q in enumerate(intervals) if not q['is_strictly_stable'] or (q['cs2_max'] is not None and q['cs2_max']>1)]
    return {
       "source_points":int(len(p)),
       "original_energy_nodes_strictly_increasing":True,
       "source_negative_cs2_knot_count":int(np.count_nonzero(source_cs2<0)),
       "source_superluminal_cs2_knot_count":int(np.count_nonzero(source_cs2>1)),
       "source_min_cs2":float(np.min(source_cs2)),
       "source_max_cs2":float(np.max(source_cs2)),
       "candidate":"SciPy PCHIP log(energy) vs log(pressure), not LAL source cubic or Steffen",
       "pchip_continuous_dloge_dlogp_min":float(min_derivative),
       "pchip_continuous_dloge_dlogp_max":float(max_derivative),
       "pchip_exact_interval_derivative_positive":bool(stable),
       "pchip_continuous_cs2_min":cs2_min,
       "pchip_continuous_cs2_max":cs2_max,
       "pchip_entire_table_causality_screen":bool(stable and cs2_max is not None and cs2_max<=1.0),
       "first_unstable_or_supraluminal_interval_index":first_bad[0] if first_bad else None,
       "first_interval_bad_type":(
           "nonpositive_derivative" if first_bad and not intervals[first_bad[0]]['is_strictly_stable']
           else "superluminal_candidate" if first_bad else None),
       "pchip_continuous_derivative_bounds_method":"exact quadratic vertex and endpoints on EVERY interval",
       "pchip_continuous_cs2_bounds_method":"stationarity polynomial roots s*(1-s)-s_prime=0 plus both endpoints",
       "scientific_status":"NUMERIC_INTERPOLANT_CANDIDATE_ONLY_NOT_PHYSICAL_EOS_CERTIFICATION",
    }


def audit_pinned(source_dir:Path, pinned_rns_json:Path) -> dict:
    raw=pinned_rns_json.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PINNED_RNS_JSON_SHA256:
        raise ValueError("Known independent 7-EOS RNS source reference JSON SHA mismatch")
    previous=json.loads(raw)
    if previous.get('validated_eos_count')!=7 or set(previous.get('eos',{}))!=set(EOS):
        raise ValueError("Pinned RNS source 7-EOS reference schema mismatch")
    results={}
    for name in EOS:
        path=source_dir/(name+'.npz')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=previous['eos'][name]['source_npz_sha256']:
            raise ValueError(f"{name}: original JESTER EOS source SHA mismatch")
        with np.load(path,allow_pickle=False) as z:
            results[name]=audit_arrays(z['p'],z['e'],z['cs2'])
        results[name]['source_npz_sha256']=digest
    return {"schema":"j0740-continuous-monotone-eos-independent-candidate-v1",
            "pinned_jester_commit":PINNED_JESTER,
            "rns_reference_json_sha256":PINNED_RNS_JSON_SHA256,
            "eos":results,
            "count_source_negative_cs2":sum(v['source_negative_cs2_knot_count']>0 for v in results.values()),
            "count_pchip_nonpositive_derivative":sum(not v['pchip_exact_interval_derivative_positive'] for v in results.values()),
            "count_pchip_superluminal_or_unstable":sum(not v['pchip_entire_table_causality_screen'] for v in results.values()),
            "caveats":["Does NOT reproduce original LAL natural-cubic derivative: candidate changes interpolation model",
                      "Strict derivative extrema are exact for polynomial representation; roots are numerical float64, not formally interval arithmetic",
                      "No P->0 low-pressure physical crust completion, no RNS rotating star, no EOS likelihood, no Bayes evidence"]}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--jester-dir',type=Path,required=True)
    ap.add_argument('--rns-reference-json',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    report=audit_pinned(args.jester_dir,args.rns_reference_json)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    for name,record in report['eos'].items():
        print(name,'SOURCE_neg',record['source_negative_cs2_knot_count'],
              'PCHIP_dloge_min',record['pchip_continuous_dloge_dlogp_min'],
              'PCHIP_cs2_max',record['pchip_continuous_cs2_max'],
              'PCHIP_full_causality',record['pchip_entire_table_causality_screen'],flush=True)
    print('PCHIP candidate is not a physical EOS proof, not an EOS posterior',flush=True)


if __name__=='__main__':main()
