#!/usr/bin/env python3
"""F134: dense *native LAL* APR4 in-star interpolation diagnostic.

Finite sampling is not a continuum proof, a stability test, or EOS evidence.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

SOURCE_SHA = "639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88"
CENTER_PRESSURE = 5.300787070483e-10  # pinned independent APR4 2.073-Msun vicinity study
JESTER_COMMIT = "e6768650ce992abfd1153a6833857572fe5cd230"


def native_api(lalsim, name):
    method = getattr(lalsim, name, None)
    if method is None:
        method = getattr(lalsim, name.replace("Geometrized", "Geometerized"), None)
    if method is None:
        raise RuntimeError(f"LAL_NATIVE_API_MISSING:{name}")
    return method


def audit(path, lalsim, points_per_interval=17):
    if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("APR4_UPSTREAM_SOURCE_SHA_MISMATCH")
    with np.load(path, allow_pickle=False) as f:
        p = np.asarray(f["p"], float)
        e = np.asarray(f["e"], float)
    if len(p) < 800 or np.any(np.diff(p) <= 0) or not np.all(np.isfinite(e)):
        raise ValueError("INVALID_SOURCE_GRID")
    if not (p[0] < CENTER_PRESSURE < p[-1]) or points_per_interval < 3:
        raise ValueError("INVALID_CENTER_OR_SAMPLING")
    eos = lalsim.SimNeutronStarEOSByName("APR4_EPP")
    derivative = native_api(lalsim, "SimNeutronStarEOSEnergyDensityDerivOfPressureGeometrized")
    energy = native_api(lalsim, "SimNeutronStarEOSEnergyDensityOfPressureGeometrized")
    edges = np.concatenate((p[p < CENTER_PRESSURE], [CENTER_PRESSURE]))
    rows = []
    for interval, (left, right) in enumerate(zip(edges[:-1], edges[1:])):
        for j in range(points_per_interval):
            if interval and j == 0:
                continue
            q = float(np.exp(np.log(left) + j * (np.log(right)-np.log(left))/(points_per_interval-1)))
            ee = float(energy(q, eos)); de = float(derivative(q, eos))
            if not all(map(math.isfinite, (ee, de))) or ee <= 0 or de == 0:
                raise ValueError(f"NATIVE_NONFINITE_OR_SINGULAR:{interval}:{j}")
            cs2 = 1/de
            rows.append((interval, j, q, ee, de, cs2))
    if not rows:
        raise RuntimeError("NO_NATIVE_MEASUREMENT")
    bad = [r for r in rows if r[5] <= 0 or r[5] > 1]
    return {
        "schema": "j0740_f134_apr4_original_lal_dense_instar_v1",
        "source_commit": JESTER_COMMIT,
        "source_npz_sha256": SOURCE_SHA,
        "center_pressure_geom_m_minus2": CENTER_PRESSURE,
        "source_intervals_scanned": len(edges)-1,
        "samples_per_interval": points_per_interval,
        "native_calls": len(rows),
        "min_cs2": min(r[5] for r in rows),
        "max_cs2": max(r[5] for r in rows),
        "native_noncausal_sample_count": len(bad),
        "first_bad_samples": [dict(interval=r[0], fraction_index=r[1], p_geom=r[2], cs2=r[5]) for r in bad[:20]],
        "interpretation": "DENSE_NATIVE_SAMPLING_ONLY_NOT_CONTINUUM_OR_PHYSICAL_EOS_CERTIFICATION",
    }, rows


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,required=True)
    ap.add_argument("--out-dir",type=Path,required=True)
    ap.add_argument("--points-per-interval",type=int,default=17)
    a=ap.parse_args()
    import lal
    import lalsimulation as lalsim
    result, rows = audit(a.source, lalsim, a.points_per_interval)
    result["lalsuite_version"] = str(getattr(lal,"__version__","unknown"))
    a.out_dir.mkdir(parents=True,exist_ok=True)
    dest=a.out_dir/"F134_NATIVE_APR4_INSTAR.json"
    dest.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    with (a.out_dir/"F134_NATIVE_APR4_INSTAR_SAMPLES.csv").open("w",newline="") as f:
        w=csv.writer(f); w.writerow(["interval","fraction_index","p_geom","e_geom","de_dp","cs2"])
        w.writerows(rows)
    print("F134_NATIVE_RESULT",json.dumps(result,sort_keys=True),flush=True)
    return 0 if result["native_noncausal_sample_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
