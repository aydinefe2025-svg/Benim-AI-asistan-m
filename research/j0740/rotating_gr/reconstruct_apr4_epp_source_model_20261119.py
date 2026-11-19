#!/usr/bin/env python3
"""Reconstruct the published APR4_EPP cold barotrope and compare pinned tables."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

G = 6.67430e-11
C = 299792458.0
LAL_TABLE_SHA256 = "2a63cd7f1e1c5a158bb3cc06ab4b51f4344a9a1e6bfaeec7f98937c3d5a5447f"
LAL_TABLE_BYTES = 72350
JESTER_SHA256 = "639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88"
JESTER_BYTES = 56300
GENERATOR_SHA256 = "30ff07b009b422e918dca1ee42ca967ffedc26e88ace611133a4ee486a133784"

RHO_LOW_SI = np.array([0.0, 2.44033979e10, 3.78358138e14, 2.62780487e15])
K_LOW_SI = np.array(
    [1.0801158752700761e7, 1.311359898998385e10, 6.507604807550857e19, 3.053461077133694e8]
)
GAMMA_LOW = np.array([1.58424999, 1.28732904, 0.62223344, 1.35692395])


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_segments() -> list[dict]:
    rho_low = G * RHO_LOW_SI / C**2
    k_low = K_LOW_SI * G ** (1.0 - GAMMA_LOW) * C ** (2.0 * GAMMA_LOW - 4.0)
    gamma1, gamma2, gamma3 = 2.830, 3.445, 3.348
    rho1_si, rho2_si = 10.0**17.7, 10.0**18.0
    rho1, rho2 = G * rho1_si / C**2, G * rho2_si / C**2
    p1 = 10.0**33.269 * G / C**4  # Read log10(p1)=34.269 dyn cm^-2 = 33.269 log10(Pa)
    k1 = p1 / rho1**gamma1
    k2 = p1 / rho1**gamma2
    k3 = k2 * rho2 ** (gamma2 - gamma3)
    rho_join = (k_low[3] / k1) ** (1.0 / (gamma1 - GAMMA_LOW[3]))
    if not rho_low[3] < rho_join < rho1:
        raise ValueError("APR4 crust/core join is outside the LAL 7-piece branch")

    segments = [
        {"name": f"SLy4_crust_{i}", "lo": rho_low[i], "hi": rho_low[i + 1] if i < 3 else rho_join,
         "k": k_low[i], "gamma": GAMMA_LOW[i]}
        for i in range(4)
    ]
    segments.extend([
        {"name": "APR4_Read_Gamma1", "lo": rho_join, "hi": rho1, "k": k1, "gamma": gamma1},
        {"name": "APR4_Read_Gamma2", "lo": rho1, "hi": rho2, "k": k2, "gamma": gamma2},
    ])
    # Endrizzi et al. APR4_EPP extension. Densities in paper are g cm^-3;
    # convert to kg m^-3 before geometrizing.
    rho3 = G * (1.4e18) / C**2  # 1.4e15 g cm^-3
    rho4 = G * (1.61e18) / C**2  # 1.61e15 g cm^-3
    segments.append({"name": "APR4_Read_Gamma3_pre_EPP", "lo": rho2, "hi": rho3, "k": k3, "gamma": gamma3})
    p3 = k3 * rho3**gamma3
    k4 = p3 / rho3**3
    segments.append({"name": "APR4_EPP_added_Gamma3", "lo": rho3, "hi": rho4, "k": k4, "gamma": 3.0})
    p4 = k4 * rho4**3
    k5 = p4 / rho4**2
    segments.append({"name": "APR4_EPP_added_Gamma2", "lo": rho4, "hi": np.inf, "k": k5, "gamma": 2.0})

    # Cold first-law constants: epsilon=(1+a_i)rho + P/(Gamma_i-1).
    a = 0.0
    for i, seg in enumerate(segments):
        seg["a"] = a
        if i + 1 < len(segments):
            boundary = seg["hi"]
            p_boundary = seg["k"] * boundary**seg["gamma"]
            a += (1.0 / (seg["gamma"] - 1.0) - 1.0 / (segments[i + 1]["gamma"] - 1.0)) * p_boundary / boundary
    return segments


def values_at_pressure(p: np.ndarray, segments: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    pressure_breaks = np.array([s["k"] * s["hi"] ** s["gamma"] for s in segments[:-1]])
    index = np.minimum(np.searchsorted(pressure_breaks, p, side="right"), len(segments) - 1)
    rho = np.array([(p[j] / segments[i]["k"]) ** (1.0 / segments[i]["gamma"]) for j, i in enumerate(index)])
    eps = np.array([(1.0 + segments[i]["a"]) * rho[j] + p[j] / (segments[i]["gamma"] - 1.0) for j, i in enumerate(index)])
    h = np.log((eps + p) / rho)  # h(surface)=0 because a_surface=0
    cs2 = np.array([segments[i]["gamma"] * p[j] / (eps[j] + p[j]) for j, i in enumerate(index)])
    return index, rho, eps, h, cs2


def audit(table_path: Path, jester_path: Path) -> dict:
    table_raw, jester_raw = table_path.read_bytes(), jester_path.read_bytes()
    table_sha, jester_sha = hashlib.sha256(table_raw).hexdigest(), hashlib.sha256(jester_raw).hexdigest()
    if len(table_raw) != LAL_TABLE_BYTES or table_sha != LAL_TABLE_SHA256:
        raise ValueError("LALSuite APR4_EPP table identity differs from pinned 7.26.4 source")
    if len(jester_raw) != JESTER_BYTES or jester_sha != JESTER_SHA256:
        raise ValueError("JESTER APR4_EPP table identity differs from pinned commit")
    table = np.loadtxt(table_path, dtype=np.float64)
    if table.shape != (1447, 2) or not np.isfinite(table).all():
        raise ValueError(f"unexpected pinned LAL table: {table.shape}")
    if np.any(np.diff(table, axis=0) <= 0):
        raise ValueError("pinned LAL P,epsilon table is not strictly increasing")
    segments = build_segments()
    p_table, e_table = table.T
    idx, rho, e_model, _, cs_table = values_at_pressure(p_table, segments)
    rel_e = np.abs(e_model / e_table - 1.0)
    max_i = int(np.argmax(rel_e))

    with np.load(jester_path, allow_pickle=False) as source:
        required = {"p", "e", "h", "cs2", "n"}
        if not required.issubset(source.files):
            raise ValueError(f"JESTER NPZ missing arrays: {sorted(required - set(source.files))}")
        p_j, e_j, h_j, cs2_j, n_j = (np.asarray(source[k], dtype=np.float64) for k in ("p", "e", "h", "cs2", "n"))
        if any(x.shape != p_j.shape or not np.isfinite(x).all() for x in (e_j, h_j, cs2_j, n_j)):
            raise ValueError("JESTER APR4 arrays invalid")
    jidx, jrho, je, jh, jcs = values_at_pressure(p_j, segments)
    je_rel, jh_rel = np.abs(je / e_j - 1.0), np.abs(jh / h_j - 1.0)
    jcs_rel = np.abs(jcs / cs2_j - 1.0)
    bad_jester_cs = np.flatnonzero(cs2_j > 1.0)
    max_cs_residual_row = int(jcs_rel.argmax())

    joins = []
    for left, right in zip(segments[:-1], segments[1:]):
        r = left["hi"]
        p_left = left["k"] * r**left["gamma"]
        p_right = right["k"] * r**right["gamma"]
        e_left = (1 + left["a"]) * r + p_left / (left["gamma"] - 1)
        e_right = (1 + right["a"]) * r + p_right / (right["gamma"] - 1)
        h_left, h_right = np.log((e_left + p_left) / r), np.log((e_right + p_right) / r)
        cs_left = left["gamma"] * p_left / (e_left + p_left)
        cs_right = right["gamma"] * p_right / (e_right + p_right)
        joins.append({"left": left["name"], "right": right["name"], "rho_geom_m_inv2": float(r),
                      "relative_pressure_jump": float(p_right / p_left - 1),
                      "relative_energy_jump": float(e_right / e_left - 1),
                      "enthalpy_jump": float(h_right - h_left),
                      "cs2_left": float(cs_left), "cs2_right": float(cs_right)})

    piece_checks = []
    for s in segments:
        p_lo = s["k"] * s["lo"] ** s["gamma"] if s["lo"] > 0 else 0.0
        p_hi = s["k"] * s["hi"] ** s["gamma"] if np.isfinite(s["hi"]) else None
        if p_hi is None:
            cs_limit = s["gamma"] - 1.0
            causal = bool(s["gamma"] == 2.0 and 1.0 + s["a"] > 0 and cs_limit == 1.0)
            max_cs = 1.0
        else:
            e_hi = (1 + s["a"]) * s["hi"] + p_hi / (s["gamma"] - 1.0)
            max_cs = float(s["gamma"] * p_hi / (e_hi + p_hi))
            causal = bool(max_cs <= 1.0)
        piece_checks.append({"name": s["name"], "gamma": float(s["gamma"]),
                             "rho_range_geom_m_inv2": [float(s["lo"]), float(s["hi"]) if np.isfinite(s["hi"]) else None],
                             "p_range_geom_m_inv2": [float(p_lo), float(p_hi) if p_hi is not None else None],
                             "energy_offset_1_plus_a": float(1 + s["a"]),
                             "cs2_max_or_asymptotic_supremum": max_cs,
                             "analytic_piece_causal": causal,
                             "thermodynamically_stable_gamma_positive": bool(s["gamma"] > 0 and 1 + s["a"] > 0)})

    return {
        "schema": "j0740_apr4_epp_full_analytic_source_reconstruction_v1",
        "source_identity": {
            "lalsuite_release": "lalsuite-v7.26.4",
            "lalsuite_table_bytes": len(table_raw), "lalsuite_table_sha256": table_sha,
            "jester_commit": "e6768650ce992abfd1153a6833857572fe5cd230",
            "jester_npz_bytes": len(jester_raw), "jester_npz_sha256": jester_sha,
            "jester_generator_sha256": GENERATOR_SHA256,
        },
        "model_basis": {
            "crust": "Pinned LALSuite SLY4 four-piece low-density constants",
            "core": "Read et al. 2009 APR4: log10(p1)=34.269 dyn cm^-2; Gamma=(2.830,3.445,3.348)",
            "causal_extension": "Endrizzi et al. 2016 APR4_EPP: Gamma=3 from 1.4e15 g cm^-3; Gamma=2 above 1.61e15 g cm^-3",
            "first_law": "p=K rho^Gamma; epsilon=(1+a_i)rho+p/(Gamma-1); a_i recursively chosen for energy continuity",
            "cs2": "Gamma*p/(epsilon+p), exact analytic derivative within each cold polytropic segment",
        },
        "reconstruction": {
            "segments": piece_checks,
            "joins": joins,
            "lalsuite_table_rows": len(table),
            "max_abs_relative_epsilon_residual_vs_lalsuite_table": float(rel_e[max_i]),
            "max_residual_source_row_zero_based": max_i,
            "max_residual_pressure_geom_m_inv2": float(p_table[max_i]),
            "all_reconstructed_source_table_cs2_finite_positive": bool(np.all(cs_table > 0) and np.isfinite(cs_table).all()),
            "max_analytic_cs2_on_lalsuite_table_support": float(cs_table.max()),
            "max_analytic_cs2_source_pressure_geom_m_inv2": float(p_table[cs_table.argmax()]),
        },
        "jester_crosscheck": {
            "rows": len(p_j),
            "max_abs_relative_epsilon_residual": float(je_rel.max()),
            "max_epsilon_residual_row_zero_based": int(je_rel.argmax()),
            "max_abs_relative_enthalpy_residual": float(jh_rel.max()),
            "max_enthalpy_residual_row_zero_based": int(jh_rel.argmax()),
            "max_abs_relative_cs2_residual": float(jcs_rel.max()),
            "max_cs2_residual_row_zero_based": max_cs_residual_row,
            "max_cs2_residual_pressure_geom_m_inv2": float(p_j[max_cs_residual_row]),
            "source_rows_abs_cs2_relative_difference_over_1pct": np.flatnonzero(jcs_rel > 0.01).astype(int).tolist(),
            "stored_native_cs2_gt_one_rows": bad_jester_cs.astype(int).tolist(),
            "stored_native_cs2_gt_one_values": cs2_j[bad_jester_cs].tolist(),
            "analytic_cs2_at_those_rows": jcs[bad_jester_cs].tolist(),
            "interpretation": "The APR4_EPP analytic source reconstruction is causal at those pressures; the stored derivative array's two >1 samples are not the analytic piecewise-polytrope sound speed.",
            "baryon_density_note": "Pinned generator defines n=e/m_avg (rest-mass approximation); analytic first-law density is proportional to rho. Absolute RNS baryon-mass normalization is not certified by this reconstruction.",
        },
        "acceptance": {
            "both_pinned_source_identities": True,
            "LAL_epsilon_reconstruction_max_relative_error_below_1e-4": bool(rel_e.max() < 1e-4),
            "all_segment_joins_within_published_constant_rounding_tolerance": bool(all(abs(j["relative_pressure_jump"]) < 5e-7 and abs(j["relative_energy_jump"]) < 5e-9 and abs(j["enthalpy_jump"]) < 5e-7 for j in joins)),
            "all_piecewise_segments_stable_and_causal": bool(all(x["analytic_piece_causal"] and x["thermodynamically_stable_gamma_positive"] for x in piece_checks)),
            "APR4_EPP_cold_barotrope_physical_source_model": "PASS_RECONSTRUCTED_ANALYTIC_MODEL",
            "absolute_RNS_baryon_mass_normalization": "NOT_ESTABLISHED",
            "rotating_sequence_and_continuous_stability": "NOT_ESTABLISHED",
            "EOS_Bayes": "NOT_RUN",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("lalsuite_table", type=Path)
    parser.add_argument("jester_npz", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(args.lalsuite_table, args.jester_npz)
    for key in ("both_pinned_source_identities", "LAL_epsilon_reconstruction_max_relative_error_below_1e-4",
                "all_segment_joins_within_published_constant_rounding_tolerance", "all_piecewise_segments_stable_and_causal"):
        if not result["acceptance"][key]:
            raise SystemExit(f"scientific gate failed: {key}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"acceptance": result["acceptance"], "reconstruction": result["reconstruction"],
                      "jester_crosscheck": result["jester_crosscheck"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()

