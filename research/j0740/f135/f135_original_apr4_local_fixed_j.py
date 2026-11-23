#!/usr/bin/env python3
"""Original JESTER APR4_EPP, direct C/RNS local constant-J sequence.

All sampled centres are below the first source superluminal knot. This does
not establish a turning point, dynamical stability, or physical EOS evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "f63"))
sys.path.insert(0, str(HERE.parent / "rotating_gr"))
from f63_original_mpa1_fixed_J import c_call, fixed_j_at_density
from jester_to_rns import from_jester_npz, write_rns

SOURCE_SHA = "639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88"
SOURCE_COMMIT = "e6768650ce992abfd1153a6833857572fe5cd230"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
ANCHOR_E = 1749731258530239.8
SPIN_HZ = 346.536369
DENSITY_E15 = (1.55, 1.65, ANCHOR_E / 1e15, 1.85, 1.95, 2.00)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_gate(source):
    if digest(source) != SOURCE_SHA:
        raise ValueError("F135_APR4_SOURCE_SHA_MISMATCH")
    with np.load(source, allow_pickle=False) as z:
        e = np.asarray(z["e"], float)
        cs2 = np.asarray(z["cs2"], float)
    bad = np.flatnonzero(cs2 > 1)
    if len(bad) != 2 or bad[0] != 812 or not np.all(np.isfinite(e)):
        raise ValueError("F135_SOURCE_CAUSALITY_GATE_DRIFT")
    if not all(0 < ec * 1e15 < float(e[bad[0]]) * (299792458.0**2/6.67430e-11)*.001 for ec in DENSITY_E15):
        raise ValueError("F135_STAR_CENTRE_REACHES_ACAUSAL_SOURCE")
    return {"first_superluminal_source_index": int(bad[0]),
            "first_superluminal_source_e_geom": float(e[bad[0]])}


def run(source, binary, out):
    gate = source_gate(source)
    table, _ = from_jester_npz(source, points=196)
    out = Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    table_path = out.parent / "APR4_EPP_F135_original_196.rns"
    write_rns(table_path, table)
    reference = c_call(binary, table_path, ANCHOR_E, frequency=SPIN_HZ)
    if not (abs(reference["mass_msun"]-2.072)<.012
            and abs(reference["radius_eq_km"]-10.76)<.12
            and abs(reference["spin_hz"]-SPIN_HZ)<.25):
        raise ValueError("F135_ORIGINAL_APR4_C_ANCHOR_MISMATCH")
    J = reference["J_cgs"]
    if not 1e44 < J < 1e52:
        raise ValueError("F135_BAD_ANCHOR_J")
    result = {"schema":"J0740_F135_ORIGINAL_APR4_LOCAL_FIXED_J_V1",
              "source_sha256":SOURCE_SHA,"source_commit":SOURCE_COMMIT,
              "rns_commit":RNS_COMMIT,"table_sha256":digest(table_path),
              "binary_sha256":digest(binary),"source_gate":gate,
              "anchor":reference,"target_J_cgs":J,"stars":[],
              "status":"IN_PROGRESS", "eos_physical_global_acceptance":"NOT_ESTABLISHED",
              "turning_point":"NOT_TESTED_ABOVE_CAUSAL_DOMAIN",
              "xpsi_photon_bayes":"NOT_RUN"}
    def save():out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    save()
    seed=.985
    for ec15 in DENSITY_E15:
        ec=ec15*1e15
        try:
            star=fixed_j_at_density(lambda ee,r:c_call(binary,table_path,ee,ratio=r),ec,J,seed)
            seed=star["axis_ratio"]
            star["source_causal_domain_sampled_centre_only"]=True
        except Exception as ex:
            star={"ec_g_cm3":ec,"status":"FAILED_FIXED_J","error":f"{type(ex).__name__}:{str(ex)[:250]}"}
        result["stars"].append(star);save()
        print("F135",ec15,star["status"],star.get("mass_msun"),flush=True)
    good=[s for s in result["stars"] if s["status"].startswith("DIRECT_C_FIXED_J")]
    result["all_six_successful"]=len(good)==len(DENSITY_E15)
    result["strictly_rising_mass_on_sampled_local_J_branch"]=len(good)==len(DENSITY_E15) and all(a["mass_msun"]<b["mass_msun"] for a,b in zip(good,good[1:]))
    result["status"]="PASS_LOCAL_NUMERICAL_FIXED_J_NOT_GLOBAL_STABILITY" if result["all_six_successful"] else "PARTIAL_FIXED_J_NOT_ACCEPTED"
    save()
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument("--source",required=True,type=Path)
    p.add_argument("--rns",required=True,type=Path);p.add_argument("--out",required=True,type=Path)
    a=p.parse_args();r=run(a.source,a.rns,a.out)
    return 0 if r["all_six_successful"] else 2


if __name__=="__main__":
    raise SystemExit(main())
