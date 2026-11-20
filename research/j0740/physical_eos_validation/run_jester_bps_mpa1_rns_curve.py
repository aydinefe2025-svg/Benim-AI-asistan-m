#!/usr/bin/env python3
"""Direct fixed-spin RNS mass-radius curve for the named BPS-MPA1 hybrid."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_jester_bps_mpa1_rns as core

MASS_GRID=np.linspace(1.89,2.175,10,dtype=float)
MASS_TOL=1e-4
RADIUS_TOL_KM=0.05

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def run(args):
    table=Path(args.eos_file)
    export=core.export_rns_eos(table)
    runs=[]
    for binary,tag in zip(args.rns_binary,args.grid_tags):
        points=[]
        for mass in MASS_GRID:
            core.TARGET_M=float(mass)
            one=core.solve_one_grid(Path(binary),table,tag)
            one["target_mass_msun"]=float(mass)
            points.append(one)
            print(json.dumps({"grid":tag,"target_mass_msun":float(mass),
                              "result":one["result"]},sort_keys=True),flush=True)
        runs.append({"grid":tag,"binary":str(binary),"binary_sha256":sha(binary),
                     "points":points})
    paired=[]
    good=True
    for k,mass in enumerate(MASS_GRID):
        a=runs[0]["points"][k]["result"]; b=runs[1]["points"][k]["result"]
        ok=(a.get("status")=="PASS" and b.get("status")=="PASS" and
            abs(a["M_msun"]-b["M_msun"])<MASS_TOL and
            abs(a["R_equatorial_km"]-b["R_equatorial_km"])<RADIUS_TOL_KM)
        good &= ok
        paired.append({"target_mass_msun":float(mass),
          "mass_difference_msun":abs(a["M_msun"]-b["M_msun"]) if "M_msun" in a and "M_msun" in b else None,
          "radius_difference_km":abs(a["R_equatorial_km"]-b["R_equatorial_km"]) if "R_equatorial_km" in a and "R_equatorial_km" in b else None,
          "passed":bool(ok)})
    out={"schema":"J0740_BPS_MPA1_FIXED_SPIN_RNS_CURVE_V1",
      "model":"JESTER_BPS_CRUST_LAL_MPA1_HIGH_PRESSURE_CROSSING_CAUSAL_TAIL_V1",
      "rns_source":{"repository":core.RNS_REPO,"commit":core.RNS_COMMIT},
      "target_spin_hz":core.TARGET_SPIN_HZ,"mass_targets_msun":MASS_GRID.tolist(),
      "rns_eos_export":export,"runs":runs,"paired_grid_checks":paired,
      "grid_convergence":{"mass_tolerance_msun":MASS_TOL,"radius_tolerance_km":RADIUS_TOL_KM,
        "passed":bool(good)},
      "status":"PASS_TWO_GRID_CURVE" if good else "FAIL_RNS_CURVE_OR_GRID_CONVERGENCE",
      "limits":{"full_source_native_xpsi":"NOT_RUN","full_eos_bayes":"NOT_RUN",
        "outside_mass_window":"NOT_INTEGRATED; no zero-tail assumption"}}
    return out

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--eos-file",type=Path,required=True)
    p.add_argument("--rns-binary",type=Path,nargs=2,required=True)
    p.add_argument("--grid-tags",nargs=2,default=["151x301","201x401"])
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); result=run(a)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print(json.dumps({"status":result["status"],"grid_convergence":result["grid_convergence"]},sort_keys=True))
    if result["status"]!="PASS_TWO_GRID_CURVE": raise SystemExit(1)
