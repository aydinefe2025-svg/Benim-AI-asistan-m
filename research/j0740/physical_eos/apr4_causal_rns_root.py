"""Source-locked causal APR4 completion -> independent RNS rotating-GR validation.

No assertion that the original APR4_EPP is globally causal. Fourth-column
normalization uses JESTER's m_avg convention only, NOT a physical mu_0.
Requires the native_lalsuite_apr4_causal_model.py source and precise RNS root
solver on the same science branch.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "rotating_gr"))
from native_lalsuite_apr4_causal_model import (
    NativeAPR4CausalEOS, sha256, LAL_TABLE_SHA, NPZ_SHA, C, G
)
from precise_apr4_mass_spin_root import (
    solve_fixed_mf, run_model, TARGET_MASS_MSUN, TARGET_SPIN_HZ,
    MASS_TOL_MSUN, SPIN_TOL_HZ
)
from jester_to_rns import write_rns

MODEL = "APR4_EPP_LALSuite_7.26.4_NATIVE_CAUSAL_COMPLETION"
RNS_SOURCE = "rns-alberta/rns@97e85d325a33e37f702306414533f6cd77812477"
JESTER_SOURCE = "nuclear-multimessenger-astronomy/jester@e6768650ce992abfd1153a6833857572fe5cd230"
SEEDS = [(1.75, .960), (1.80, .965)]

def validate_source(table: Path, npz: Path):
    if sha256(table) != LAL_TABLE_SHA:
        raise ValueError("Pinned LALSuite 7.26.4 APR4 EOS table SHA256 mismatch")
    if sha256(npz) != NPZ_SHA:
        raise ValueError("Pinned JESTER APR4 NPZ SHA256 mismatch")
    with np.load(npz, allow_pickle=False) as z:
        e = np.asarray(z["e"], dtype=float)
        n = np.asarray(z["n"], dtype=float)
    if not np.isfinite(e).all() or not np.isfinite(n).all() or not np.all(n > 0):
        raise ValueError("Bad native number-density reference")
    mavg = float(e[0] / n[0])
    if not 1e-56 < mavg < 1e-52:
        raise ValueError("Unexpected JESTER numerical m_avg convention")
    return mavg

def make_rows(eos, mavg_geom_m: float, points: int):
    if not 100 <= points <= 200:
        raise ValueError("RNS supports at most 200 EOS input nodes")
    pmax = max(4 * eos.pcut, 1.5e-9)
    p = np.geomspace(eos.p0, pmax, points)
    e = np.array([eos.energy(float(x)) for x in p])
    h = np.array([eos.h(float(x)) for x in p])
    # The n convention is arbitrary by one global constant absent mu_0.
    n = (e + p) * np.exp(-h) / mavg_geom_m
    rows = np.column_stack((
        e * C*C/G * 1e-3,       # geometric energy [m^-2] -> rho [g/cm^3]
        p * C**4/G * 10.,     # geometric pressure [m^-2] -> P [dyne/cm^2]
        h * (C*100)**2 + 1., # dimensionless integrated enthalpy -> H [cm^2/s^2]
        n / 1e6,              # m^-3 -> cm^-3
    ))
    if not np.isfinite(rows).all() or np.any(rows <= 0):
        raise ValueError("Nonfinite / nonpositive RNS thermodynamics")
    if any(not np.all(np.diff(rows[:, j]) > 0) for j in range(4)):
        raise ValueError("Nonmonotonic native causal RNS table")
    if not eos.p0 < eos.pcut < pmax:
        raise ValueError("Invalid causal transition for RNS pressure coverage")
    # Source continuity: h(p) & n(p) must not jump across causal switch.
    cut = eos.pcut
    for scale in (1-1e-8, 1+1e-8):
        x = cut * scale
        if abs(eos.energy(x) / eos.energy(cut) - 1) > 1e-6:
            raise ValueError("Causal-completion energy boundary discontinuity")
        if abs(eos.h(x) / eos.h(cut) - 1) > 1e-6:
            raise ValueError("Causal-completion enthalpy boundary discontinuity")
    return rows, {
        "points": points,
        "pmin_geom_m_minus_2": float(p[0]),
        "pmax_geom_m_minus_2": float(p[-1]),
        "pcut_geom_m_minus_2": float(eos.pcut),
        "causal_completion": MODEL,
        "absolute_physical_baryon_normalization": "NOT_ESTABLISHED",
        "n_reference": "JESTER m_avg conversion only; M0 not physical"
    }

def run_seeds(binary: Path, table: Path, seed_list):
    out = {"binary_sha256": sha256(binary),
           "table_sha256": sha256(table),
           "seeds": [], "failures": []}
    for seed in seed_list:
        try:
            ans = solve_fixed_mf(
                lambda ec, ratio: run_model(binary, table, ec, ratio),
                seed
            )
            out["seeds"].append(ans)
        except Exception as exc:
            out["failures"].append({
                "seed": list(seed),
                "reason": type(exc).__name__ + ": " + str(exc),
                "trace": getattr(exc, "trace", [])
            })
    if len(out["seeds"]) == len(seed_list):
        a, b = out["seeds"]
        out["same_mesh_pass"] = (
            abs(a["radius_eq_km"] - b["radius_eq_km"]) < 0.001
            and abs(a["mass_msun"] - b["mass_msun"]) <= 2*MASS_TOL_MSUN
            and abs(a["spin_hz"] - b["spin_hz"]) <= 2*SPIN_TOL_HZ
        )
    else:
        out["same_mesh_pass"] = False
    return out

def perform(table: Path, npz: Path, coarse: Path, fine: Path, work: Path,
            output: Path):
    record = {
        "schema": "j0740-source-locked-APR4-causal-completion-RNS-v1",
        "status": "IN_PROGRESS",
        "model": MODEL,
        "inputs": {"native_lal_sha256": LAL_TABLE_SHA,
                   "source_jester_npz_sha256": NPZ_SHA,
                   "rns_upstream": RNS_SOURCE,
                   "jester_upstream": JESTER_SOURCE},
        "target": {"mass_msun": TARGET_MASS_MSUN, "spin_hz": TARGET_SPIN_HZ},
        "RNS_M0": "NOT_PHYSICAL_NO_MU0",
        "native_15D_XPSI_photon_bayes": "NOT_RUN",
        "experiments": {},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(record, indent=2, sort_keys=True)+"\n",
                          encoding="utf-8")
    save()
    try:
        mavg = validate_source(table, npz)
        eos = NativeAPR4CausalEOS(table)
        record["inputs"]["mavg_geom_m_JESTER_convention"] = mavg
        record["inputs"]["first_causal_crossing_p"] = float(eos.pcut)
        for N in (196, 200):
            rows, meta = make_rows(eos, mavg, N)
            filename = work / ("APR4_CAUSAL_7p26p4_" + str(N) + ".rns")
            write_rns(filename, rows)
            meta["rns_table_sha256"] = sha256(filename)
            record["experiments"][str(N)] = {"conversion": meta, "grids": {}}
            save()
        for label, binary, npoints in (
            ("151x301_196", coarse, 196),
            ("201x401_196", fine, 196),
            ("151x301_200", coarse, 200),
        ):
            filename = work / ("APR4_CAUSAL_7p26p4_" + str(npoints) + ".rns")
            rec = run_seeds(binary, filename, SEEDS)
            record["experiments"][str(npoints)]["grids"][label] = rec
            save()
        a = record["experiments"]["196"]["grids"]["151x301_196"]
        b = record["experiments"]["196"]["grids"]["201x401_196"]
        c = record["experiments"]["200"]["grids"]["151x301_200"]
        converged = a["same_mesh_pass"] and b["same_mesh_pass"] and c["same_mesh_pass"]
        if converged:
            x, y, z = (g["seeds"][0] for g in (a, b, c))
            d_mesh = abs(x["radius_eq_km"] - y["radius_eq_km"])
            d_eos = abs(x["radius_eq_km"] - z["radius_eq_km"])
            record["radius_spatial_mesh_delta_km"] = d_mesh
            record["radius_eos_grid_delta_km"] = d_eos
            converged = d_mesh < .02 and d_eos < .02
            record["rotating_root_fine"] = {
                key: y[key] for key in
                ("mass_msun", "radius_eq_km", "spin_hz",
                 "central_energy_density_g_cm3", "axis_ratio")
            }
        record["status"] = (
            "PASS_CAUSAL_CANDIDATE_TWO_MESH_AND_EOS_GRID"
            if converged else "FAIL_OR_INCOMPLETE_CANDIDATE_RNS_ROOT"
        )
    except Exception as exc:
        record["status"] = "FAILED_VALIDATION_NO_PHYSICAL_CLAIM"
        record["error"] = type(exc).__name__ + ": " + str(exc)
        save()
        raise
    save()
    return record

def _selftest():
    class ToyEOS:
        p0=1e-24
        pcut=1e-9
        def energy(self,p):return 1e-6*(p/1e-10)**0.6
        def h(self,p):return .01*(p/1e-10)**0.4
    fake=ToyEOS()
    rows, meta = make_rows(fake, 1e-54, 196)
    assert rows.shape == (196, 4)
    assert np.all(np.diff(rows, axis=0) > 0)
    assert meta["absolute_physical_baryon_normalization"] == "NOT_ESTABLISHED"
    try:
        make_rows(fake, 1e-54, 201)
    except ValueError:
        pass
    else:
        raise AssertionError("RNS upper row bound not enforced")
    fake.pcut=1e-24
    try:
        make_rows(fake, 1e-54, 196)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid causal crossing was not rejected")
    print("SELFTEST_PASS: 196 rows; positive monotonic 4 cols; bounds; source threshold")

if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--table",type=Path)
    ap.add_argument("--npz",type=Path)
    ap.add_argument("--binary-coarse",type=Path)
    ap.add_argument("--binary-fine",type=Path)
    ap.add_argument("--work",type=Path)
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:
        _selftest()
    else:
        for x in ("table","npz","binary_coarse","binary_fine","work","out"):
            if getattr(args,x) is None:ap.error("--"+x.replace("_","-")+" required")
        outcome=perform(args.table,args.npz,args.binary_coarse,args.binary_fine,
                        args.work,args.out)
        print(json.dumps({"status":outcome["status"],
                          "root":outcome.get("rotating_root_fine"),
                          "deltas":{k:v for k,v in outcome.items() if "delta_km" in k}},
                         indent=2))
        if not outcome["status"].startswith("PASS"):
            raise SystemExit(2)