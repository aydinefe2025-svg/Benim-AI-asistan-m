"""Check what RNS actually receives near JESTER's negative crust cs² knot.

Use only pinned small upstream JESTER NPZ EOS and previously verified seven-star
GR JSON, without touching the 12.9 GB Salmi photon-data archive. No native
X-PSI likelihood or astrophysical EOS model evidence is evaluated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from jester_to_rns import C, G, from_jester_npz, write_rns

EOS = ("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")
JESTER_SHA = "e6768650ce992abfd1153a6833857572fe5cd230"
RNS_JSON_SHA = "d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"
RNS_RUN = 42353019033
PRESSURE_CONVERSION_CGS = C**4 / G * 10.0
RHO_CONVERSION_CGS = C**2 / G * 1e-3
C2_CGS = (C * 100.0)**2


def rns_p_at_e_cubic_cs2(rows: np.ndarray, target_rho: float) -> dict:
    """Exact algebraic derivative of PINNED RNS C four-point log(p) vs log(e) interpolation.

    Mirrors equil.c::p_at_e and equil_util.c::interp, including the 4-point
    clamped bracket. The actual C solver separately calls e_at_p and p_at_h.
    """
    a=np.asarray(rows,dtype=float)
    if (a.ndim!=2 or a.shape[1]!=4 or len(a)<4
            or not math.isfinite(target_rho)
            or not a[0,0]<=target_rho<=a[-1,0]
            or np.any(np.diff(a[:,0])<=0) or np.any(np.diff(a[:,1])<=0)):
        raise ValueError("Invalid RNS table for four-point interpolation")
    x=np.log10(a[:,0])
    y=np.log10(a[:,1])
    z=math.log10(target_rho)
    j=int(np.searchsorted(x,z,side="right")-1)
    start=max(0,min(j-1,len(x)-4))
    xp=x[start:start+4]
    yp=y[start:start+4]
    value=0.0
    derivative=0.0
    for i in range(4):
        other=[q for q in range(4) if q!=i]
        denominator=math.prod(float(xp[i]-xp[q]) for q in other)
        basis=math.prod(float(z-xp[q]) for q in other)/denominator
        deriv_basis=sum(math.prod(float(z-xp[q]) for q in other if q!=m)
                        for m in other)/denominator
        value+=float(yp[i])*basis
        derivative+=float(yp[i])*deriv_basis
    pressure=10.0**value
    cs2=pressure/(target_rho*C2_CGS)*derivative
    if not all(math.isfinite(v) for v in (pressure,derivative,cs2)):
        raise ValueError("Nonfinite C-style cubic EOS derivative")
    return {
        "cs2_over_c2":float(cs2),
        "dlogp_dlogrho":float(derivative),
        "pressure_cgs":float(pressure),
        "c_interpolation_row_indices":[start,start+1,start+2,start+3],
    }


def profile_c_interpolant(rows: np.ndarray, center_rho: float, per_interval=8) -> dict:
    """Densely sample RNS C p_at_e derivative below rotating center; no interval proof."""
    if not 2<=per_interval<=64:
        raise ValueError("Invalid sampling density")
    rho=np.asarray(rows)[:,0]
    if not rho[0]<center_rho<rho[-1]:
        raise ValueError("Center outside table")
    stop=int(np.searchsorted(rho,center_rho))
    points=[]
    for j in range(stop):
        lo=float(rho[j])
        hi=min(float(rho[j+1]),float(center_rho))
        if hi>lo:
            points.extend(np.geomspace(lo,hi,per_interval,endpoint=False).tolist())
    points.append(float(center_rho))
    values=[rns_p_at_e_cubic_cs2(rows,r)["cs2_over_c2"] for r in points]
    min_idx=int(np.argmin(values))
    max_idx=int(np.argmax(values))
    negative_rhos=[float(rho) for rho,v in zip(points,values) if v<0]
    return {
        "sample_count":len(values),
        "min_cs2_over_c2":float(min(values)),
        "max_cs2_over_c2":float(max(values)),
        "min_cs2_rho_g_cm3":float(points[min_idx]),
        "max_cs2_rho_g_cm3":float(points[max_idx]),
        "negative_cs2_rho_range_g_cm3":[min(negative_rhos),max(negative_rhos)] if negative_rhos else None,
        "negative_sample_count":int(len(negative_rhos)),
        "superluminal_sample_count":int(sum(v>1 for v in values)),
        "sampling_caveat":"8 samples per table interval plus center. No proof of global bounds between points.",
    }


def analyze_transfer(source_e_geo, source_p_geo, native_cs2, table_rows, center_rho):
    """Separate native analytic derivative from positive RNS INPUT secants.

    Only intervals with both density endpoints below the rotating center are
    called wholly within the star. The bracket straddling center is reported
    but not classified as wholly interior. This does not assert what spline
    derivatives the compiled RNS C code may take between table knots.
    """
    e = np.asarray(source_e_geo, dtype=float)
    p = np.asarray(source_p_geo, dtype=float)
    cs2 = np.asarray(native_cs2, dtype=float)
    rows = np.asarray(table_rows, dtype=float)
    if (e.ndim != 1 or len(e) < 8 or p.shape != e.shape or cs2.shape != e.shape
            or rows.ndim != 2 or rows.shape[1] != 4 or len(rows) < 8
            or any(np.any(~np.isfinite(x)) for x in (e, p, cs2, rows))
            or np.any(e <= 0) or np.any(p <= 0) or np.any(rows <= 0)
            or np.any(np.diff(p) <= 0) or np.any(np.diff(rows[:,0]) <= 0)
            or np.any(np.diff(rows[:,1]) <= 0) or not math.isfinite(center_rho)
            or center_rho <= 0 or center_rho <= rows[0, 0]
            or center_rho >= rows[-1, 0]):
        raise ValueError("Invalid source/source-matched RNS input or star center")
    rho = e * RHO_CONVERSION_CGS
    rns_rho = rows[:, 0]
    rns_p = rows[:, 1]
    dcs2 = np.diff(rns_p) / (np.diff(rns_rho) * C2_CGS)
    if np.any(~np.isfinite(dcs2)) or np.any(dcs2 <= 0):
        raise ValueError("Nonpositive or nonfinite RNS input secant sound speed")
    in_star = rns_rho[1:] <= center_rho
    if not np.any(in_star):
        raise ValueError("No RNS segments wholly below star center")
    negative_idxs = np.flatnonzero(cs2 < 0)
    source_reversal_edges = np.flatnonzero(np.diff(e) <= 0)
    details = []
    for k in negative_idxs:
        p_k = float(p[k] * PRESSURE_CONVERSION_CGS)
        if not rns_p[0] <= p_k <= rns_p[-1]:
            raise ValueError("Negative source knot pressure outside RNS input range")
        j = min(max(0, int(np.searchsorted(rns_p, p_k, side="right") - 1)), len(rns_p) - 2)
        # In a logarithmic-thermodynamic table this means an input pressure
        # interval, NOT exact representation of its analytic source derivative.
        p_span_factor = float(rns_p[j + 1] / rns_p[j])
        logrho_at_p = float(np.interp(np.log(p_k), np.log(rns_p), np.log(rns_rho)))
        approx_rho = math.exp(logrho_at_p)
        native_rho = float(rho[k])
        details.append({
            "source_index": int(k),
            "native_analytic_cs2_over_c2": float(cs2[k]),
            "native_rho_g_cm3": native_rho,
            "native_p_dyn_cm2": p_k,
            "rns_bracketing_row_indices": [j, j + 1],
            "rns_bracketing_pressures_dyn_cm2": [float(rns_p[j]), float(rns_p[j + 1])],
            "rns_pressure_bracket_ratio": p_span_factor,
            "rns_secant_cs2_over_c2_at_knot_pressure": float(dcs2[j]),
            "rns_interpolated_rho_at_source_knot_p_g_cm3": approx_rho,
            "rns_interpolated_rho_relative_difference": (approx_rho-native_rho)/native_rho,
            "native_negative_derivative_has_positive_rns_secant": bool(dcs2[j] > 0),
            "below_rotating_center": bool(native_rho < center_rho),
        })
    native_supra_idxs = np.flatnonzero((cs2 > 1.0) & (rho <= center_rho))
    rns_supra = np.flatnonzero((dcs2 > 1.0) & in_star)
    center_cubic=rns_p_at_e_cubic_cs2(rows,center_rho)
    cubic_profile=profile_c_interpolant(rows,center_rho,per_interval=8)
    for v in details:
        knot=rns_p_at_e_cubic_cs2(rows,v["native_rho_g_cm3"])
        v["rns_c_p_at_e_four_point_cubic_at_native_knot"]=knot
        v["original_native_p_vs_rns_c_p_at_e_cubic_relative_difference"]=(
            knot["pressure_cgs"]-v["native_p_dyn_cm2"])/v["native_p_dyn_cm2"]
    return {
        "rns_p_at_e_four_point_cubic_at_rotating_center":center_cubic,
        "rns_p_at_e_four_point_cubic_through_center_sample":cubic_profile,
        "rns_p_at_e_source":"Pinned rns-alberta/rns equil.c p_at_e uses equil_util.c 4-point Lagrange log interpolation",
        "rns_c_cubic_not_other_rns_e_at_p_or_p_at_h_warning":"The solver separately calls p_at_h and e_at_p; only p_at_e directly differentiated here.",
        "native_negative_cs2_nodes": len(details),
        "native_energy_density_nonincreasing_edges": int(len(source_reversal_edges)),
        "native_nonincreasing_edge_indices": [int(v) for v in source_reversal_edges[:15]],
        "native_negative_node_mapping": details,
        "rns_eos_input_point_count": len(rows),
        "rns_input_secant_cs2_min": float(dcs2.min()),
        "rns_input_secant_cs2_max_all_tabulated": float(dcs2.max()),
        "rns_input_secant_cs2_max_wholly_below_center": float(dcs2[in_star].max()),
        "rns_input_nonpositive_secant_count": int(np.count_nonzero(dcs2 <= 0)),
        "rns_input_supraluminal_secants_wholly_below_center": int(len(rns_supra)),
        "native_supraluminal_nodes_below_center": int(len(native_supra_idxs)),
        "native_source_negative_knot_present_but_rns_secants_positive": bool(
            details and all(v["native_negative_derivative_has_positive_rns_secant"] for v in details)),
        "caveat": "Positive input secants alone do not establish stability. The independently differentiated four-point RNS C p_at_e interpolant is one EOS operation, not the full equilibrium p_at_h/e_at_p, and cannot prove causality or eliminate the native source defect.",
    }


def audit(previous_rns, source_dir: Path, output_dir: Path):
    if (previous_rns.get("status") != "ALL_SEVEN_VALIDATED"
            or previous_rns.get("validated_eos_count") != 7
            or previous_rns.get("jester_upstream_commit") != JESTER_SHA
            or set(previous_rns.get("eos", {})) != set(EOS)):
        raise ValueError("Pinned verified 7-EOS GR model source identities mismatch")
    data = {}
    for name in EOS:
        record = previous_rns["eos"][name]
        source = source_dir / f"{name}.npz"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != record["source_npz_sha256"]:
            raise ValueError(f"{name}: original source-NPZ SHA mismatch")
        if record["status"] != "MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED":
            raise ValueError(f"{name}: source RNS model not validated")
        rows, meta = from_jester_npz(source, points=196)
        table = output_dir / f"{name}_source_196pt.rns"
        write_rns(table, rows)
        with np.load(source, allow_pickle=False) as raw:
            e, p, cs2 = (raw[k] for k in ("e", "p", "cs2"))
        center = record["rns_rotating_at_target"]["central_energy_density_g_cm3"]
        outcome = analyze_transfer(e, p, cs2, rows, center)
        # 200pt representation check uses same pinned source and historical
        # star central density. NO new C/GR solver call is made here.
        rows200,meta200=from_jester_npz(source,points=200)
        out200=analyze_transfer(e,p,cs2,rows200,center)
        table200=output_dir/f"{name}_source_200pt.rns"
        write_rns(table200,rows200)
        outcome["comparison_200pt_input_without_new_GR_run"]=out200
        outcome["rns_200pt_input_sha256"]=hashlib.sha256(table200.read_bytes()).hexdigest()
        outcome.update({
            "source_npz_sha256": digest,
            "rns_input_sha256_regenerated_this_run": hashlib.sha256(table.read_bytes()).hexdigest(),
            "rns_input_sha256_from_prior_verified_GR_run": record["rns_table_sha256"],
            "rns_input_sha_matches_previous_GR_run": hashlib.sha256(table.read_bytes()).hexdigest() == record["rns_table_sha256"],
            "rotating_model_center_g_cm3": float(center),
            "source_row_count": meta["source_points"],
        })
        data[name] = outcome
        print(name, "source_bad", outcome["native_negative_cs2_nodes"],
              "RNS_bad_secants", outcome["rns_input_nonpositive_secant_count"],
              "star_inner_supraluminal", outcome["rns_input_supraluminal_secants_wholly_below_center"],
              flush=True)
    return {
        "schema": "j0740-native-eos-crust-negative-node-rns-input-transfer-v2",
        "status": "PINNED_SEVEN_EOS_RAW_VS_RNS_INPUT_CRUST_KNOT_TRANSFER_CHECK_COMPLETE_NOT_BAYES",
        "source_jester_commit": JESTER_SHA,
        "source_full_GR_run": RNS_RUN,
        "source_GR_json_sha256": RNS_JSON_SHA,
        "num_models_checked": len(data),
        "source_models_with_negative_native_cs2": sum(v["native_negative_cs2_nodes"] > 0 for v in data.values()),
        "rns_models_with_nonpositive_input_secants": sum(v["rns_input_nonpositive_secant_count"] > 0 for v in data.values()),
        "rns_models_with_supraluminal_input_secants_below_center": sum(v["rns_input_supraluminal_secants_wholly_below_center"] > 0 for v in data.values()),
        "models_with_negative_c_p_at_e_samples_196":sum(
            v["rns_p_at_e_four_point_cubic_through_center_sample"]["negative_sample_count"]>0
            for v in data.values()),
        "models_with_negative_c_p_at_e_samples_200":sum(
            v["comparison_200pt_input_without_new_GR_run"]["rns_p_at_e_four_point_cubic_through_center_sample"]["negative_sample_count"]>0
            for v in data.values()),
        "models_with_superluminal_c_p_at_e_at_center_196":sum(
            v["rns_p_at_e_four_point_cubic_at_rotating_center"]["cs2_over_c2"]>1
            for v in data.values()),
        "models_with_superluminal_c_p_at_e_at_center_200":sum(
            v["comparison_200pt_input_without_new_GR_run"]["rns_p_at_e_four_point_cubic_at_rotating_center"]["cs2_over_c2"]>1
            for v in data.values()),
        "numerical_scope":"Pinned C/RNS four-point p_at_e interpolation derivative sampled below center, compared for 196 and 200 thermodynamic input points; not a new GR solve, full e_at_p/p_at_h proof, or EOS Bayes evidence",
        "eos": data,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rns-json", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    raw = args.rns_json.read_bytes()
    if hashlib.sha256(raw).hexdigest() != RNS_JSON_SHA:
        raise ValueError("Pinned RNS JSON SHA identity mismatch")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    evidence = audit(json.loads(raw), args.source_dir, args.out.parent)
    args.out.write_text(json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(evidence["status"], flush=True)


if __name__ == "__main__":
    main()
