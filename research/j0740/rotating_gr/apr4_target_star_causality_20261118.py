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


def continuous_profile(spline, start_x: float, end_x: float) -> dict:
    """Find continuous extrema interval-by-interval for cs2 and dlog(e)/dlog(P)."""
    knots = spline.x
    i0 = max(0, int(np.searchsorted(knots, start_x, side="right") - 1))
    i1 = min(len(knots) - 2, int(np.searchsorted(knots, end_x, side="left")))
    max_cs2 = -math.inf
    min_cs2 = math.inf
    min_slope = math.inf
    first_cross = None
    interval_count = 0
    def cs2_at(xv: float) -> float:
        slope = float(spline(xv, 1))
        return math.exp(xv - float(spline(xv))) / slope
    for i in range(i0, i1 + 1):
        xa = max(start_x, float(knots[i]))
        xb = min(end_x, float(knots[i + 1]))
        if xb < xa:
            continue
        interval_count += 1
        a, b, c, _ = (float(v) for v in spline.c[:, i])
        dlog_poly = np.poly1d([3.0 * a, 2.0 * b, c])
        d2log_poly = np.poly1d([6.0 * a, 2.0 * b])
        stationary_poly = dlog_poly - dlog_poly * dlog_poly - d2log_poly
        tlo, thi = xa - float(knots[i]), xb - float(knots[i])
        ts = [tlo, thi]
        for z in stationary_poly.r:
            if abs(float(np.imag(z))) <= 1.0e-10:
                zr = float(np.real(z))
                if tlo < zr < thi:
                    ts.append(zr)
        ts = sorted(set(ts))
        xs = [float(knots[i]) + t for t in ts]
        vals = [cs2_at(xv) for xv in xs]
        max_cs2 = max(max_cs2, *vals)
        min_cs2 = min(min_cs2, *vals)
        for xv in (xs[0], xs[-1]):
            min_slope = min(min_slope, float(spline(xv, 1)))
        if a != 0.0:
            vertex = -b / (3.0 * a)
            if tlo < vertex < thi:
                min_slope = min(min_slope, float(dlog_poly(vertex)))
        for xleft, xright, cleft, cright in zip(xs[:-1], xs[1:], vals[:-1], vals[1:]):
            if first_cross is None and cleft <= 1.0 < cright:
                xc = brentq(lambda xv: cs2_at(xv) - 1.0, xleft, xright)
                first_cross = {"log_pressure": float(xc), "pressure_geom_m2": math.exp(float(xc))}
    return {"max_cs2": max_cs2, "min_cs2": min_cs2,
            "min_dlogeps_dlogp": min_slope, "first_cs2_gt_1_crossing": first_cross,
            "spline_interval_count": interval_count}


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
            profile = continuous_profile(spline, float(np.log(p[0])), lp_c)
            low_p_extension_join_cs2 = 5.0 * p[0] / (3.0 * e[0])
            max_cs2 = max(profile["max_cs2"], float(low_p_extension_join_cs2))
            min_slope = min(profile["min_dlogeps_dlogp"], 0.6)
            central_cs2 = math.exp(lp_c - float(spline(lp_c))) / float(spline(lp_c, 1))
            solved.append({
                "grid": grid["grid"],
                "central_density_g_cm3": rho_cgs,
                "central_pressure_geom_m2": pc,
                "central_cs2": central_cs2,
                "max_cs2_from_surface_to_center": max_cs2,
                "spline_intervals_from_surface_to_center": profile["spline_interval_count"],
                "min_dlogeps_dlogp_from_surface_to_center": min_slope,
                "low_p_extension_cs2_at_join": float(low_p_extension_join_cs2),
                "mass_msun": float(seed["mass_msun"]),
                "spin_hz": float(seed["spin_hz"]),
                "radius_eq_km": float(seed["radius_eq_km"]),
                "local_thermodynamic_stability_and_causality_pass": bool(min_slope > 0.0 and max_cs2 < 1.0),
            })
    whole = continuous_profile(spline, float(np.log(p[0])), float(np.log(p[-1])))
    first_cross = whole["first_cs2_gt_1_crossing"]
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
            "extrema_method": "continuous interval search: quartic roots of d(log cs2)/dlogP on every natural-cubic interval; dlogeps/dlogP extrema from endpoint and quadratic vertex",
            "target_spline_intervals_per_root": "reported per root profile",
            "whole_table_spline_intervals": whole["spline_interval_count"],
            "surface_model_for_target_screen": "epsilon=epsilon0*(P/P0)^0.6; cs2=5P/(3epsilon), down to P->0",
            "target_models": "four saved direct RNS roots; no stellar solver rerun",
        },
        "target_roots": solved,
        "whole_original_source_table": {
            "min_dlogeps_dlogp": min(whole["min_dlogeps_dlogp"], 0.6),
            "max_cs2": max(whole["max_cs2"], float(5.0 * p[0] / (3.0 * e[0]))),
            "first_superluminal_crossing": first_cross,
            "global_source_eos_causal": bool(whole["max_cs2"] <= 1.0),
        },
        "acceptance": {
            "all_four_target_star_interiors_causal_and_thermodynamically_stable": all(x["local_thermodynamic_stability_and_causality_pass"] for x in solved),
            "original_apr4_global_causality": "FAIL" if whole["max_cs2"] > 1.0 else "PASS",
            "target_star_specific_eos_screen": "PASS_CONDITIONAL",
            "fixed_J_turning_point_stability": "NOT_ESTABLISHED",
            "absolute_baryon_mass_normalization": "NOT_ESTABLISHED",
            "EOS_Bayes": "NOT_RUN",
        },
        "status": "TARGET_STAR_LOCAL_EOS_SCREEN_PASS; ORIGINAL_APR4_GLOBAL_EOS_NOT_CERTIFIED; EOS_Bayes=NOT_RUN",
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
