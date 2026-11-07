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
    return {
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
        "caveat": "RNS input secants are not the derivatives of the internal C RNS EOS interpolant; positive input secants do NOT establish physical stability, causality or eliminate the original source defect.",
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
        "schema": "j0740-native-eos-crust-negative-node-rns-input-transfer-v1",
        "status": "PINNED_SEVEN_EOS_RAW_VS_RNS_INPUT_CRUST_KNOT_TRANSFER_CHECK_COMPLETE_NOT_BAYES",
        "source_jester_commit": JESTER_SHA,
        "source_full_GR_run": RNS_RUN,
        "source_GR_json_sha256": RNS_JSON_SHA,
        "num_models_checked": len(data),
        "source_models_with_negative_native_cs2": sum(v["native_negative_cs2_nodes"] > 0 for v in data.values()),
        "rns_models_with_nonpositive_input_secants": sum(v["rns_input_nonpositive_secant_count"] > 0 for v in data.values()),
        "rns_models_with_supraluminal_input_secants_below_center": sum(v["rns_input_supraluminal_secants_wholly_below_center"] > 0 for v in data.values()),
        "numerical_scope": "Strictly observed EOS table *secants*, not derivative of RNS internal spline or physical EOS model Bayes evidence",
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
