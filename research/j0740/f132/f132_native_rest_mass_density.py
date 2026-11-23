#!/usr/bin/env python3
"""F132: original LALSimulation EOS baryon/rest-mass-density vs JESTER approximation.

Independent source-native diagnostics only. Does NOT infer EOS posterior/evidence,
validate rotating-star stability, or change source EOS tables.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

EOS_NAMES = ("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")
JESTER_COMMIT = "e6768650ce992abfd1153a6833857572fe5cd230"
BARYON_MASS_AVG_MEV = (939.5654205203889 + 938.2720881604904) / 2.0
J_TO_MEV = 1e6 * 1.602176634e-19


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_api(lalsim, name: str):
    """Prefer the current spelling; accept documented legacy spelling only."""
    obj = getattr(lalsim, name, None)
    if obj is not None:
        return obj
    if name.endswith("Geometrized"):
        obj = getattr(lalsim, name.replace("Geometrized", "Geometerized"), None)
    if obj is None:
        raise RuntimeError(f"SOURCE_LAL_API_MISSING:{name}")
    return obj


def require_source_data(data: dict) -> dict:
    keys = ("p", "e", "h", "n", "cs2", "dloge_dlogp")
    out = {}
    for key in keys:
        if key not in data:
            raise ValueError(f"JESTER_SOURCE_KEY_MISSING:{key}")
        a = np.asarray(data[key], dtype=np.float64)
        if a.ndim != 1 or len(a) < 100 or not np.all(np.isfinite(a)):
            raise ValueError(f"JESTER_SOURCE_INVALID:{key}")
        out[key] = a
    sizes = {len(a) for a in out.values()}
    if len(sizes) != 1 or np.any(np.diff(out["p"]) <= 0):
        raise ValueError("JESTER_SOURCE_INVALID_GRID")
    for x in ("p", "e", "h", "n"):
        if np.any(out[x] <= 0):
            raise ValueError(f"JESTER_SOURCE_NONPOSITIVE:{x}")
    return out


def summary_stats(arr: np.ndarray) -> dict:
    arr = np.asarray(arr, dtype=np.float64)
    if arr.size == 0 or not np.all(np.isfinite(arr)):
        raise ValueError("NONFINITE_SUMMARY")
    return {"min": float(arr.min()), "median": float(np.median(arr)),
            "p05": float(np.quantile(arr, .05)), "p95": float(np.quantile(arr, .95)),
            "max": float(arr.max())}


def measure_one(eos_name: str, path: Path, lal, lalsim):
    if not path.is_file():
        raise FileNotFoundError(f"NO_SOURCE_NPZ:{path}")
    with np.load(path, allow_pickle=False) as archive:
        arrays = require_source_data(archive)
    eos = lalsim.SimNeutronStarEOSByName(eos_name)
    geom_m = BARYON_MASS_AVG_MEV * J_TO_MEV / lal.C_SI**2 * lal.G_SI / lal.C_SI**2
    if not math.isfinite(geom_m) or geom_m <= 0:
        raise ValueError("INVALID_GEOMETRIC_BARYON_MASS")
    f_h = select_api(lalsim, "SimNeutronStarEOSPseudoEnthalpyOfPressureGeometrized")
    f_e = select_api(lalsim, "SimNeutronStarEOSEnergyDensityOfPressureGeometrized")
    f_de = select_api(lalsim, "SimNeutronStarEOSEnergyDensityDerivOfPressureGeometrized")
    f_rho = select_api(lalsim, "SimNeutronStarEOSRestMassDensityOfPseudoEnthalpyGeometrized")
    rows = []
    failed = []
    for i, p in enumerate(arrays["p"]):
        try:
            hh = float(f_h(float(p), eos))
            ee = float(f_e(float(p), eos))
            de = float(f_de(float(p), eos))
            rr = float(f_rho(hh, eos))
            if not all(math.isfinite(a) and a > 0 for a in (hh, ee, de, rr)):
                raise ValueError("NONPOSITIVE_NATIVE_OUTPUT")
            n_native = rr / geom_m
            if n_native <= 0:
                raise ValueError("BAD_NATIVE_NUMBER_DENSITY")
            rows.append({"index": i, "p_geom": float(p), "e_jester": float(arrays["e"][i]),
                         "e_lal": ee, "h_jester": float(arrays["h"][i]), "h_lal": hh,
                         "n_jester_approx": float(arrays["n"][i]), "n_lal_rest": n_native,
                         "n_lal_geom_rest_density": rr,
                         "cs2_jester": float(arrays["cs2"][i]), "cs2_lal": 1.0 / de,
                         "native_de_dp": de})
        except Exception as exc:
            failed.append({"index": i, "pressure": float(p), "error": f"{type(exc).__name__}:{str(exc)[:200]}"})
    if len(rows) < 100:
        raise RuntimeError(f"NATIVE_EOS_INSUFFICIENT_VALID_POINTS:{eos_name}:{len(rows)}/{len(arrays['p'])}")
    native = np.array([r["n_lal_rest"] for r in rows]); approx = np.array([r["n_jester_approx"] for r in rows])
    e = np.array([r["e_lal"] for r in rows]); p = np.array([r["p_geom"] for r in rows]); h=np.array([r["h_lal"] for r in rows]);
    rho=np.array([r["n_lal_geom_rest_density"] for r in rows])
    log_mu_minus_h = np.log((e+p)/rho) - h
    mu_resid = np.abs(log_mu_minus_h-np.median(log_mu_minus_h))
    e_rel=np.array([abs(r["e_jester"]/r["e_lal"]-1) for r in rows]);
    h_rel=np.array([abs(r["h_jester"]/r["h_lal"]-1) for r in rows]);
    raw_cs2=np.array([r["cs2_lal"] for r in rows]);
    result = {"eos": eos_name, "source_npz_sha256": sha(path), "source_points": len(arrays["p"]),
              "native_valid_points": len(rows), "native_failed_points": len(failed),
              "native_failures_first10": failed[:10],
              "n_native_over_jester_approx": summary_stats(native/approx),
              "n_absolute_fraction_difference": summary_stats(np.abs(native/approx - 1)),
              "source_e_relative_difference": summary_stats(e_rel),
              "source_h_relative_difference": summary_stats(h_rel),
              "native_cs2": summary_stats(raw_cs2),
              "jester_cs2_nonpositive_count":int(np.sum(arrays["cs2"]<=0)),
              "jester_dloge_nonpositive_count":int(np.sum(arrays["dloge_dlogp"]<=0)),
              "native_cs2_superluminal_count": int(np.sum(raw_cs2>1.0)),
              "native_cs2_nonpositive_count": int(np.sum(raw_cs2<=0.0)),
              "log_mu_minus_h_median_centered_absolute_error":summary_stats(mu_resid),
              "claim_limit":"LAL rest-mass density was sourced using the original EOS; its normalization/thermodynamic construction is LAL version-dependent. This does not physically certify RNS EOS or photon-native Bayes."}
    return result,rows


def main(argv=None):
    a=argparse.ArgumentParser()
    a.add_argument("--jester-dir", type=Path,required=True)
    a.add_argument("--out-dir", type=Path,required=True)
    args=a.parse_args(argv)
    import lal
    import lalsimulation as lalsim
    out=args.out_dir
    out.mkdir(parents=True,exist_ok=True)
    all_results={"schema":"J0740_F132_7_NATIVE_LAL_ORIGINAL_EOS_REST_MASS_DENSITY_V1",
                 "jester_source_commit":JESTER_COMMIT,
                 "lalsuite_version":str(getattr(lal,"__version__","unknown")),
                 "scientific_status":"SOURCE_NATIVE_NUMERICAL_DIAGNOSTIC_NOT_EOS_BAYES",
                 "model_results":{}, "failed_models":{}}
    ledger={}
    for name in EOS_NAMES:
        path=args.jester_dir/f"{name}.npz"
        try:
            result,rows=measure_one(name,path,lal,lalsim)
            csvpath=out/f"{name}_native_n_comparison.csv"
            with csvpath.open("w",newline="") as file:
                w=csv.DictWriter(file,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)
            all_results["model_results"][name]=result
            ledger[csvpath.name]=sha(csvpath)
            print("F132_NATIVE_MODEL",name,json.dumps({"points":result["native_valid_points"],"n_ratio":result["n_native_over_jester_approx"],"max_cs2":result["native_cs2"]["max"],"failed":result["native_failed_points"]}),flush=True)
        except Exception as exc:
            all_results["failed_models"][name]=f"{type(exc).__name__}:{str(exc)[:350]}"
            print("F132_MODEL_FAIL_CLOSED",name,all_results["failed_models"][name],flush=True)
    all_results["overall_acceptance"] = "ALL_SEVEN_NATIVE_LAL_QUERIES_COMPLETE" if len(all_results["model_results"]) == 7 and all(x["native_failed_points"]==0 for x in all_results["model_results"].values()) else "PARTIAL_NATIVE_SOURCE_INCOMPLETE_NOT_CERTIFIED"
    report=out/"F132_REAL_LAL_SEVEN_SOURCE_NATIVE_REPORT.json";report.write_text(json.dumps(all_results,sort_keys=True,indent=2)+"\n")
    ledger[report.name]=sha(report)
    manifest=out/"F132_SHA256.json";manifest.write_text(json.dumps({"files":ledger,"source_ref":JESTER_COMMIT},sort_keys=True,indent=2)+"\n")
    print("F132_RESULT",all_results["overall_acceptance"],"models",len(all_results["model_results"]),"failures",all_results["failed_models"],flush=True)
    return 0 if all_results["overall_acceptance"]=="ALL_SEVEN_NATIVE_LAL_QUERIES_COMPLETE" else 2

if __name__ == "__main__":sys.exit(main())