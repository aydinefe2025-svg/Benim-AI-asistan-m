from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq

TABLE_SHA256 = "2a63cd7f1e1c5a158bb3cc06ab4b51f4344a9a1e6bfaeec7f98937c3d5a5447f"
ROOT_SHA256 = "0065c93bbb95b4d0d05a5a934b541f782169c2f7f52123edeaed1ff89da00bb4"
G_SI = 6.67430e-11
C_SI = 299792458.0

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def audit(table_path: Path, roots_path: Path) -> dict:
    if sha(table_path) != TABLE_SHA256:
        raise ValueError("official LALSuite table SHA-256 mismatch")
    if sha(roots_path) != ROOT_SHA256:
        raise ValueError("saved direct-root JSON SHA-256 mismatch")
    table = np.loadtxt(table_path)
    if table.shape != (1447, 2):
        raise ValueError(f"unexpected APR4 table shape: {table.shape}")
    p, e = table[:, 0], table[:, 1]
    if not (np.all(np.isfinite(table)) and np.all(np.diff(p) > 0) and np.all(np.diff(e) > 0)):
        raise ValueError("APR4 table must be finite and strictly increasing")
    spline = CubicSpline(np.log(p), np.log(e), bc_type="natural")
    roots = json.loads(roots_path.read_text(encoding="utf-8"))
    if roots.get("sources", {}).get("rns_eos_table_sha256", "").lower() != "c8f4da82524a5e0b3450c682198359078deb78d573a1f50f2487235df16d88c7":
        raise ValueError("root table identity mismatch")
    solved = []
    for grid in roots["spatial_grids"]:
        for seed in grid["seeds"]:
            rho_cgs = float(seed["central_energy_density_g_cm3"])
            eps_geom = rho_cgs * 1000.0 * G_SI / C_SI**2
            lp_c = brentq(lambda lp: float(spline(lp)) - math.log(eps_geom),
                          float(np.log(p[0])), float(np.log(p[-1])))
            pc = math.exp(lp_c)
            lp = np.linspace(float(np.log(p[0])), lp_c, 50001)
            pp = np.exp(lp)
            ee = np.exp(spline(lp))
            dlog = spline(lp, 1)
            cs2 = pp / (ee * dlog)
            low_p_extension_join_cs2 = 5.0 * p[0] / (3.0 * e[0])
            max_cs2 = max(float(np.max(cs2)), float(low_p_extension_join_cs2))
            solved.append({
                "grid": grid["grid"],
                "central_density_g_cm3": rho_cgs,
                "central_pressure_geom_m2": pc,
                "central_cs2": float(cs2[-1]),
                "max_cs2_from_surface_to_center": max_cs2,
                "min_dlogeps_dlogp_from_surface_to_center": float(np.min(dlog)),
                "low_p_extension_cs2_at_join": float(low_p_extension_join_cs2),
                "mass_msun": float(seed["mass_msun"]),
                "spin_hz": float(seed["spin_hz"]),
                "radius_eq_km": float(seed["radius_eq_km"]),
                "local_stability_and_causality_pass": bool(np.all(dlog > 0.0) and max_cs2 < 1.0),
            })
    whole_lp = np.linspace(float(np.log(p[0])), float(np.log(p[-1])), 250001)
    whole_p = np.exp(whole_lp)
    whole_e = np.exp(spline(whole_lp))
    whole_d = spline(whole_lp, 1)
    whole_cs2 = whole_p / (whole_e * whole_d)
    crossings = np.flatnonzero(whole_cs2 > 1.0)
    first_cross = None
    if len(crossings):
        j = int(crossings[0])
        first_cross = {"pressure_geom_m2": float(whole_p[j]), "cs2": float(whole_cs2[j])}
    return {
        "schema": "j0740_apr4_target_star_causality_audit_v1",
        "source": {
            "lalsuite_tag": "lalsuite-v7.26.4",
            "lalsuite_release_commit": "fc92814767cd01523d546a07d325b1dd6759a1a0",
            "table_rows": int(len(table)),
            "table_sha256": sha(table_path),
            "root_evidence_sha256": sha(roots_path),
            "root_table_sha256": roots["sources"]["rns_eos_table_sha256"],
        },
        "method": {
            "interpolation": "natural cubic spline in log(epsilon)-log(P), identical to tabular replay convention",
            "cs2": "P / (epsilon * d(log epsilon)/d(log P))",
            "sample_count_per_target": 50001,
            "whole_table_sample_count": int(len(whole_lp)),
            "surface_model_for_target_screen": "epsilon=epsilon0*(P/P0)^0.6; cs2=5P/(3epsilon), down to P->0",
            "target_models": "four saved direct RNS roots; no stellar solver rerun",
        },
        "target_roots": solved,
        "whole_original_source_table": {
            "min_dlogeps_dlogp": float(np.min(whole_d)),
            "max_cs2": float(np.max(whole_cs2)),
            "first_superluminal_crossing": first_cross,
            "global_source_eos_causal": bool(np.all(whole_cs2 <= 1.0)),
        },
        "acceptance": {
            "all_four_target_star_interiors_causal_and_stable": all(x["local_stability_and_causality_pass"] for x in solved),
            "original_apr4_global_causality": "FAIL" if np.any(whole_cs2 > 1.0) else "PASS",
            "target_star_specific_eos_screen": "PASS_CONDITIONAL",
            "fixed_J_turning_point_stability": "NOT_ESTABLISHED",
            "absolute_baryon_mass_normalization": "NOT_ESTABLISHED",
            "EOS_Bayes": "NOT_RUN",
        },
        "status": "TARGET_CONFIG_CAUSAL_STABLE_TO_CENTER; ORIGINAL_APR4_GLOBAL_EOS_NOT_CERTIFIED; EOS_Bayes=NOT_RUN",
    }

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", type=Path, required=True)
    ap.add_argument("--roots", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    result = audit(a.table, a.roots)
    raw = json.dumps(result, indent=2, sort_keys=True).encode("utf-8")
    a.output.write_bytes(raw)
    print(json.dumps({"status": result["status"], "acceptance": result["acceptance"],
                      "roots": result["target_roots"], "whole_source": result["whole_original_source_table"],
                      "result_bytes": len(raw), "result_sha256": hashlib.sha256(raw).hexdigest()}, indent=2))

if __name__ == "__main__":
    main()
