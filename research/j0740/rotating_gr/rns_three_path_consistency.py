"""Cross-audit three PINNED RNS C tabulated EOS lookup paths without new GR solves.

Only uses JESTER NPZ source thermodynamics and immutable seven-EOS RNS model
JSON (Actions 42353019033); NO 12.9 GB NICER/XMM photon archive.

Equil.c in rns-alberta/rns 97e85d325a33e37f702306414533f6cd77812477
uses equil_util.c interp: 4-point Lagrange polynomial in log10 quantities.
We reproduce and analytically differentiate e_at_p (the RNS hydro path),
p_at_e and h_at_p/p_at_h inverse paths. A finite sample is NOT a global
causality or thermodynamic-consistency proof. No EOS Bayesian posterior.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from jester_to_rns import from_jester_npz, write_rns

EOS = ("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")
JESTER_COMMIT = "e6768650ce992abfd1153a6833857572fe5cd230"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
RNS_JSON_SHA256 = "d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"
C2_CGS = (299792458.0*100)**2


def interp_four_log(table_x: np.ndarray, table_y: np.ndarray, target: float, *, allow_extrapolation=False) -> dict:
    """C equil_util.c::interp Lagrange 4-pt log10 interpolation and dlogy/dlogx.

    The exact floating-point binary interpolation order is not guaranteed,
    but the polynomial and bracket match pinned upstream C code.
    """
    x, y = np.asarray(table_x, float), np.asarray(table_y, float)
    if (x.ndim != 1 or y.ndim != 1 or x.size != y.size or x.size < 4
            or not math.isfinite(target) or target <= 0
            or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y))
            or np.any(x <= 0) or np.any(y <= 0)
            or np.any(np.diff(x) <= 0) or (not allow_extrapolation and (target < x[0] or target > x[-1]))):
        raise ValueError("Invalid C tabulated EOS inputs or out-of-support query")
    xp = np.log10(x); yp = np.log10(y); z = math.log10(target)
    j = int(np.searchsorted(xp, z, side="right")-1)
    start = max(0, min(j-1, len(xp)-4))
    xs, ys = xp[start:start+4], yp[start:start+4]
    value = slope = 0.0
    for i in range(4):
        others = [q for q in range(4) if q != i]
        denominator = math.prod(float(xs[i]-xs[k]) for k in others)
        valbasis = math.prod(float(z-xs[k]) for k in others)/denominator
        gradbasis = sum(math.prod(float(z-xs[k]) for k in others if k!=m)
                        for m in others)/denominator
        value += float(ys[i])*valbasis
        slope += float(ys[i])*gradbasis
    beyond = bool(target < x[0] or target > x[-1])
    log_beyond = (math.log10(float(x[0]/target)) if target < x[0] else
                  (math.log10(float(target/x[-1])) if target > x[-1] else 0.0))
    out = 10.0**value
    if not math.isfinite(out) or not math.isfinite(slope) or out <= 0:
        raise ValueError("C tabular interpolation nonfinite/negative")
    return {"value": float(out), "dlogy_dlogx":float(slope),
            "source_table_four_row_indices": [start,start+1,start+2,start+3],
            "outside_tabulated_support":beyond,
            "extrapolation_log10_decades":log_beyond}


def at_pressure(rows: np.ndarray, target_p: float) -> dict:
    """e_at_p, h_at_p, and p_at_e/p_at_h round trips, respecting cgs units."""
    rows = np.asarray(rows, dtype=float)
    if rows.ndim != 2 or rows.shape[1] != 4 or rows.shape[0] < 4:
        raise ValueError("RNS EOS table has wrong shape")
    e, p, h = rows[:,0], rows[:,1], rows[:,2]
    energy = interp_four_log(p,e,target_p)  # upstream equil.c e_at_p
    h_at_p = interp_four_log(p,h,target_p)
    if not energy["dlogy_dlogx"]:
        raise ValueError("Zero de/dp slope in RNS e_at_p")
    cs2 = target_p/(energy["value"]*C2_CGS*energy["dlogy_dlogx"])
    # Upstream RNS C::interp permits four-point polynomial extrapolation.
    # The overrun here is a diagnostic, not permission to silently call the
    # resulting EOS physically causal or observationally validated.
    p_back_e = interp_four_log(e,p,energy["value"],allow_extrapolation=True)
    p_back_h = interp_four_log(h,p,h_at_p["value"],allow_extrapolation=True)
    return {
        "e_at_p_density_g_cm3":energy["value"],
        "e_at_p_dloge_dlogp":energy["dlogy_dlogx"],
        "e_at_p_effective_cs2_over_c2":float(cs2),
        "h_at_p_erg_per_g":h_at_p["value"],
        "p_at_e_roundtrip_pressure_dyn_cm2":p_back_e["value"],
        "p_at_h_roundtrip_pressure_dyn_cm2":p_back_h["value"],
        "h_at_p_dlogh_dlogp":h_at_p["dlogy_dlogx"],
        "p_at_e_roundtrip_relative_error": (p_back_e["value"]-target_p)/target_p,
        "p_at_h_roundtrip_relative_error": (p_back_h["value"]-target_p)/target_p,
        "e_at_p_intermediate_density_outside_input_support":p_back_e["outside_tabulated_support"],
        "h_at_p_intermediate_enthalpy_outside_input_support":p_back_h["outside_tabulated_support"],
        "p_at_e_extrapolation_log10_decades":p_back_e["extrapolation_log10_decades"],
        "p_at_h_extrapolation_log10_decades":p_back_h["extrapolation_log10_decades"],
        "p_at_e_roundtrip_relative_error_abs": abs(p_back_e["value"]-target_p)/target_p,
        "p_at_h_roundtrip_relative_error_abs": abs(p_back_h["value"]-target_p)/target_p,
    }


def table_profile(rows: np.ndarray, target_center_rho:float, samples_per_interval:int=8) -> dict:
    rows=np.asarray(rows,float)
    if (rows.ndim!=2 or rows.shape[1]!=4 or rows.shape[0]<30
            or not np.all(np.isfinite(rows)) or np.any(rows<=0)
            or not all(np.all(np.diff(rows[:,j])>0) for j in (0,1,2))
            or not 2<=samples_per_interval<=16):
        raise ValueError("Invalid RNS table or sampling configuration")
    p_from_center = interp_four_log(rows[:,0],rows[:,1],target_center_rho)["value"]
    ps = rows[:,1]
    pts=[]
    for i in range(len(ps)-1):
        lo = float(ps[i]); hi=min(float(ps[i+1]),p_from_center)
        if lo>=p_from_center:break
        if hi>lo:
            pts.extend(np.geomspace(lo,hi,samples_per_interval,endpoint=False).tolist())
    pts.append(float(p_from_center))
    sample=[]
    for p in pts:
        d=at_pressure(rows,p)
        sample.append(d)
    sound=np.asarray([x["e_at_p_effective_cs2_over_c2"] for x in sample])
    e_slopes=np.asarray([x["e_at_p_dloge_dlogp"] for x in sample])
    h_slopes=np.asarray([x["h_at_p_dlogh_dlogp"] for x in sample])
    pe=np.asarray([x["p_at_e_roundtrip_relative_error_abs"] for x in sample])
    ph=np.asarray([x["p_at_h_roundtrip_relative_error_abs"] for x in sample])
    worst_e = int(np.argmax(pe))
    worst_h = int(np.argmax(ph))
    return {
        "sample_count": len(pts),
        "low_surface_input_h_cgs": float(rows[0,2]),
        "second_input_h_cgs": float(rows[1,2]),
        "first_four_h_cgs": [float(z) for z in rows[:4,2]],
        "first_four_p_dyn_cm2": [float(z) for z in rows[:4,1]],
        "source_input_nodes": len(ps),
        "max_sample_pressure_dyn_cm2": p_from_center,
        "e_at_p_effective_cs2_center": float(sound[-1]),
        "e_at_p_cs2_min":float(sound.min()),
        "e_at_p_cs2_max":float(sound.max()),
        "e_at_p_negative_cs2_count":int((sound<0).sum()),
        "e_at_p_superluminal_cs2_count":int((sound>1).sum()),
        "e_at_p_negative_dloge_dlogp_count":int((e_slopes<0).sum()),
        "h_at_p_negative_dlogh_dlogp_count":int((h_slopes<0).sum()),
        "max_p_at_e_roundtrip_relative_error": float(pe.max()),
        "max_p_at_h_roundtrip_relative_error": float(ph.max()),
        "max_p_at_h_inverse_error_input_pressure": float(pts[worst_h]),
        "max_p_at_h_inverse_error_reconstructed_pressure": float(sample[worst_h]["p_at_h_roundtrip_pressure_dyn_cm2"]),
        "max_p_at_h_inverse_error_input_h": float(sample[worst_h]["h_at_p_erg_per_g"]),
        "max_p_at_h_inverse_error_input_rho": float(sample[worst_h]["e_at_p_density_g_cm3"]),
        "max_p_at_e_inverse_error_input_pressure": float(pts[worst_e]),
        "max_p_at_e_inverse_error_input_rho": float(sample[worst_e]["e_at_p_density_g_cm3"]),
        "e_at_p_density_out_of_support_samples":sum(int(z["e_at_p_intermediate_density_outside_input_support"]) for z in sample),
        "h_at_p_enthalpy_out_of_support_samples":sum(int(z["h_at_p_intermediate_enthalpy_outside_input_support"]) for z in sample),
        "max_p_at_e_extrapolation_decades":max(z["p_at_e_extrapolation_log10_decades"] for z in sample),
        "max_p_at_h_extrapolation_decades":max(z["p_at_h_extrapolation_log10_decades"] for z in sample),
        "rho_at_min_e_at_p_cs2_g_cm3": float(sample[int(np.argmin(sound))]["e_at_p_density_g_cm3"]),
        "p_at_min_e_at_p_cs2_dyn_cm2": float(pts[int(np.argmin(sound))]),
        "rho_at_max_e_at_p_cs2_g_cm3": float(sample[int(np.argmax(sound))]["e_at_p_density_g_cm3"]),
        "sample_caveat":"8 values/pressure-bin plus star center; C 4-point polynomial can extrapolate outside density/enthalpy table. No global proof between samples or full GR eigenstability",
    }


def audit(rns:dict,source_dir:Path,outdir:Path)->dict:
    if not(rns.get("status")=="ALL_SEVEN_VALIDATED"
           and rns.get("validated_eos_count")==7
           and rns.get("jester_upstream_commit")==JESTER_COMMIT
           and rns.get("rns_upstream_commit")==RNS_COMMIT
           and set(rns.get("eos",{}))==set(EOS)):
        raise ValueError("Seven EOS verified GR source JSON identity mismatch")
    out={}
    for name in EOS:
        record=rns["eos"][name]
        src=source_dir/(name+".npz")
        sha=hashlib.sha256(src.read_bytes()).hexdigest()
        if sha!=record["source_npz_sha256"]:raise ValueError(name+": source NPZ SHA mismatch")
        center=float(record["rns_rotating_at_target"]["central_energy_density_g_cm3"])
        o={"source_npz_sha256":sha,"rotating_center_rho_g_cm3":center,
           "rns_verified_196_input_sha256":record["rns_table_sha256"]}
        for size in (196,200):
            rows,_=from_jester_npz(src,points=size)
            dest=outdir/(name+"_"+str(size)+".rns")
            write_rns(dest,rows)
            o[str(size)+"_input_text_sha256_reproduced_this_run"]=hashlib.sha256(dest.read_bytes()).hexdigest()
            o[str(size)+"_table_profile"]=table_profile(rows,center)
        out[name]=o
        print(name,"196cs2_min",round(o["196_table_profile"]["e_at_p_cs2_min"],6),
              "200cs2_min",round(o["200_table_profile"]["e_at_p_cs2_min"],6),
              "196 max h inverse error",o["196_table_profile"]["max_p_at_h_roundtrip_relative_error"],flush=True)
    return {"schema":"j0740-RNS-real-thermo-hydrodynamics-paths-v1",
            "status":"SEVEN_RNS_EQ_C_THERMODYNAMIC_LOOKUP_PATHS_AUDITED_NOT_BAYES",
            "jester_pinned_commit":JESTER_COMMIT,
            "rns_pinned_commit":RNS_COMMIT,
            "original_seven_rns_run":42353019033,
            "original_rns_json_sha256":RNS_JSON_SHA256,
            "models_with_negative_e_at_p_196":sum(v["196_table_profile"]["e_at_p_negative_cs2_count"]>0 for v in out.values()),
            "models_with_negative_e_at_p_200":sum(v["200_table_profile"]["e_at_p_negative_cs2_count"]>0 for v in out.values()),
            "models_with_supraluminal_e_at_p_196":sum(v["196_table_profile"]["e_at_p_superluminal_cs2_count"]>0 for v in out.values()),
            "models_with_supraluminal_e_at_p_200":sum(v["200_table_profile"]["e_at_p_superluminal_cs2_count"]>0 for v in out.values()),
            "c_methods":"equil.c e_at_p, p_at_e, h_at_p, p_at_h via equil_util.c interp 4-point Lagrange in log10; reproduce polynomial and bracket analytically",
            "limitations":"RNS C source method replicated in Python, not C binary instrumented at each thermodynamic query. Finite sampling. No original gamma 15D native prior likelihood or EOS Bayes inference.",
            "eos":out}


def main():
    q=argparse.ArgumentParser()
    q.add_argument("--rns-json",type=Path,required=True)
    q.add_argument("--jester-dir",type=Path,required=True)
    q.add_argument("--out",type=Path,required=True)
    a=q.parse_args()
    raw=a.rns_json.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=RNS_JSON_SHA256:
        raise ValueError("Original RNS seven-EOS JSON sha mismatch")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    d=audit(json.loads(raw),a.jester_dir,a.out.parent)
    a.out.write_text(json.dumps(d,indent=2,sort_keys=True)+"\n")
    print(d["status"],flush=True)


if __name__=="__main__":main()
