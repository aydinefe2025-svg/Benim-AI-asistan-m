#!/usr/bin/env python3
"""F105: direct native RNS C fixed-J local peak probe on a fifth mesh."""
from __future__ import annotations
import argparse, hashlib, io, json, math, subprocess, sys, zipfile
from pathlib import Path
from scipy.optimize import brentq
import numpy as np

F104_ZIP_SHA = "b36198ac43fbd786cb1a7bc0022a7c69e35f30160242d0e2d28bbc0f662fcf02"
F105_RESULT = "F104/F104_301x601_LOCAL_PEAK.json"
F104_JOURNAL = "F104/F104_301x601_LOCAL_PEAK.jsonl"
F103_ZIP_SHA = "1491d406b68886522c514c7a08e40ef6e673cf8d48e86c6666c390a96eb11f30"
F103_RESULT = "F103/F103_251x501_LOCAL_PEAK.json"
F103_JOURNAL = "F103/F103_251x501_LOCAL_PEAK.jsonl"
F102_ZIP_SHA = "d52c186306c8a7bda8a1490fd61a68b7eb5f7fbfcd201ad1b0c21ba2af301f1a"
F102_JSON = "F102_ORIGINAL_24_PLUS_F101_1_PLUS_F102_3_REAL_C_STARS.json"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
TARGET_J = 4.8245626795750385e48
J_REL_TOL = 3e-5
GRID = "401x801"
RHO = np.array([2.55e15, 2.62e15, 2.69e15, 2.76e15, 2.83e15, 2.90e15, 2.97e15])
RATIOS = (0.999, 0.995, 0.990, 0.985, 0.980, 0.975, 0.970, 0.965,
          0.960, 0.950, 0.940, 0.925, 0.910, 0.890)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_baseline(path: Path):
    raw = path.read_bytes()
    if sha(raw) != F103_ZIP_SHA:
        raise ValueError("F103_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as z:
        current = json.loads(z.read(F103_RESULT))
        journal_bytes = z.read(F103_JOURNAL)
        if sha(journal_bytes) != current["journal_sha256"]:
            raise ValueError("F103_RAW_JOURNAL_SHA_MISMATCH")
        journal = [json.loads(x) for x in journal_bytes.decode().splitlines()]
        stars = current["new_native_C_stars"]
        if current.get("status") != "THIRD_MESH_LOCAL_SAMPLED_TURN_PASS":
            raise ValueError("F103_THIRD_MESH_NOT_ACCEPTED")
        if len(stars) != 7 or len(journal) != current.get("new_native_C_call_count") or len(journal) != 71:
            raise ValueError("F103_THIRD_MESH_RECEIPT_COUNTS_MISMATCH")
        if current.get("EOS_sha256") != EOS_SHA or current.get("target_J_cgs") != TARGET_J:
            raise ValueError("F103_PHYSICAL_INPUTS_CHANGED")
        if any(not r.get("real_native_RNS_C") for r in journal):
            raise ValueError("F103_JOURNAL_NOT_NATIVE_C")
        for star in stars:
            group = [r for r in journal if r["index"] == star["index"]]
            if len(group) != star["native_C_evaluations"] or not any(
                abs(r["r_ratio"] - star["r_ratio"]) < 1e-12
                and abs(r["M_msun"] - star["M_msun"]) < 1e-12
                and abs(r["J_cgs"] - star["J_cgs"]) / star["J_cgs"] < 1e-14 for r in group
            ):
                raise ValueError("F103_FINAL_ROOT_NOT_FOUND_IN_RAW_C_JOURNAL")
            if star["J_relative_error"] > J_REL_TOL:
                raise ValueError("F103_FINAL_J_ACCEPTANCE_FAIL")
        old_bytes = z.read("F102/F102_PR763.zip")
    if sha(old_bytes) != F102_ZIP_SHA:
        raise ValueError("EMBEDDED_F102_ARTIFACT_SHA_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(old_bytes)) as old:
        base = json.loads(old.read(F102_JSON))
    count = sum(len(v["stars"]) for v in base["both_native_C_grids"].values())
    if count != 28 or base.get("same_F99_derived_cold_EOS_sha256") != EOS_SHA or base.get("same_target_J_cgs") != TARGET_J:
        raise ValueError("F102_28_NATIVE_C_BASELINE_FAIL")
    return current, base

def call_rns(binary: Path, eos: Path, rho: float, ratio: float) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "f81"))
    from f81_exact_mass_spin import parse_rns
    cmd=[str(binary.resolve()),"-f",str(eos),"-e",f"{rho:.14e}","-r",f"{ratio:.12f}"]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=240)
    if p.returncode != 0:
        raise RuntimeError("RNS_NATIVE_C_FAILED "+p.stdout[-240:]+p.stderr[-240:])
    star=parse_rns(p.stdout)
    if abs(star["rho_c_g_cm3"]/rho-1.0)>1e-9:
        raise ValueError("NATIVE_C_CENTRAL_DENSITY_MISMATCH")
    return star

def solve_one(binary:Path,eos:Path,rho:float,journal:Path,index:int)->dict:
    trials=[]
    def evaluate(ratio:float)->float:
        star=call_rns(binary,eos,rho,ratio)
        rec={"mesh":GRID,"index":index,"rho_g_cm3":rho,"r_ratio":ratio,
             "M_msun":star["M_msun"],"R_eq_km":star["R_equatorial_km"],
             "f_hz":star["spin_hz"],"J_cgs":star["J_cgs"],
             "J_relative_error":abs(star["J_cgs"]/TARGET_J-1.0),"real_native_RNS_C":True}
        trials.append(rec)
        with journal.open("a",encoding="utf-8") as f:f.write(json.dumps(rec,allow_nan=False)+"\n")
        return star["J_cgs"]/TARGET_J-1.0
    prev=None;bracket=None;selected=None;error=None
    for ratio in RATIOS:
        error=evaluate(ratio)
        if abs(error)<=J_REL_TOL:
            selected=ratio;break
        if prev is not None and prev[1]*error<0:
            bracket=(prev[0],ratio);break
        prev=(ratio,error)
    if bracket is None and selected is None:raise RuntimeError("NATIVE_C_FIXED_J_BRACKET_NOT_FOUND")
    if bracket is not None:
        selected=brentq(evaluate,*sorted(bracket),xtol=1e-10,rtol=5e-13,maxiter=65)
        error=evaluate(selected)
    if error is None or abs(error)>J_REL_TOL:raise RuntimeError("NATIVE_C_FIXED_J_TOLERANCE_FAIL")
    final=next((r for r in reversed(trials) if math.isclose(r["r_ratio"],selected,rel_tol=0,abs_tol=1e-12)),None)
    if final is None:raise RuntimeError("FINAL_NATIVE_C_RECEIPT_MISSING")
    return {"index":index,"rho_g_cm3":rho,"r_ratio":selected,"M_msun":final["M_msun"],
       "R_eq_km":final["R_eq_km"],"f_hz":final["f_hz"],"J_cgs":final["J_cgs"],
       "J_relative_error":final["J_relative_error"],"native_C_evaluations":len(trials),
       "real_native_RNS_C":True,"journal_rows":len(trials)}

def read_f104(path: Path):
    raw=path.read_bytes()
    if sha(raw)!=F104_ZIP_SHA: raise ValueError("F104_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as z:
        current=json.loads(z.read(F104_RESULT))
        journal_bytes=z.read(F104_JOURNAL)
        if sha(journal_bytes)!=current["journal_sha256"]: raise ValueError("F105_RAW_JOURNAL_SHA_MISMATCH")
        journal=[json.loads(x) for x in journal_bytes.decode().splitlines()]
        stars=current["new_native_C_stars"]
        if current.get("status")!="FOURTH_MESH_LOCAL_SAMPLED_TURN_PASS" or current.get("mesh")!="301x601":
            raise ValueError("F104_FOURTH_MESH_NOT_ACCEPTED")
        if len(stars)!=7 or len(journal)!=71 or current.get("new_native_C_call_count")!=71:
            raise ValueError("F104_RECEIPT_COUNTS_MISMATCH")
        if current.get("EOS_sha256")!=EOS_SHA or current.get("target_J_cgs")!=TARGET_J:
            raise ValueError("F104_PHYSICAL_INPUTS_CHANGED")
        if any(not r.get("real_native_RNS_C") for r in journal): raise ValueError("F104_JOURNAL_NOT_NATIVE_C")
        for star in stars:
            group=[r for r in journal if r["index"]==star["index"]]
            if len(group)!=star["native_C_evaluations"] or not any(
                abs(r["r_ratio"]-star["r_ratio"])<1e-12 and abs(r["M_msun"]-star["M_msun"])<1e-12
                and abs(r["J_cgs"]-star["J_cgs"])/star["J_cgs"]<1e-14 for r in group):
                raise ValueError("F104_FINAL_ROOT_NOT_FOUND_IN_RAW_C_JOURNAL")
            if star["J_relative_error"]>J_REL_TOL: raise ValueError("F104_FINAL_J_ACCEPTANCE_FAIL")
    return current

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--f103",type=Path,required=True);ap.add_argument("--f104",type=Path,required=True);ap.add_argument("--eos",type=Path,required=True)
    ap.add_argument("--rns",type=Path,required=True);ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    prior,base=read_baseline(a.f103);prior4=read_f104(a.f104)
    if sha(a.eos.read_bytes())!=EOS_SHA:raise ValueError("F99_DERIVED_EOS_SHA_MISMATCH")
    if not a.rns.is_file() or len(str(a.eos))>60:raise ValueError("RNS_OR_EOS_MISSING_OR_PATH_TOO_LONG")
    journal=a.out.with_suffix(".jsonl")
    if journal.exists():raise FileExistsError("NEVER_OVERWRITE_F105_RAW_C_JOURNAL")
    rows=[];errors=[]
    for i,rho in enumerate(RHO):
        try:
            row=solve_one(a.rns,a.eos,float(rho),journal,i);rows.append(row)
            print("F105_NATIVE_C_FIXED_J_PASS",i,row["M_msun"],row["J_relative_error"],row["native_C_evaluations"],flush=True)
        except Exception as exc:
            errors.append({"index":i,"rho_g_cm3":float(rho),"error":repr(exc)})
            print("F105_NATIVE_C_POINT_FAIL_RETAINED",i,repr(exc),flush=True)
    slopes=np.diff([r["M_msun"] for r in rows])/np.diff([r["rho_g_cm3"]/1e15 for r in rows]) if len(rows)>1 else np.array([])
    peak_idx=int(np.argmax([r["M_msun"] for r in rows])) if rows else None
    turn=bool(len(rows)==7 and peak_idx is not None and 0<peak_idx<6 and np.any(slopes>0) and np.any(slopes<0))
    status="FIFTH_MESH_LOCAL_SAMPLED_TURN_PASS" if not errors and turn else "FAIL_CLOSED"
    peak=rows[peak_idx] if peak_idx is not None else None
    prior_peak=prior["local_sampled_peak"]
    previous={g:v["measured_slope"] for g,v in base["both_native_C_grids"].items()}
    previous["251x501"]=prior_peak
    previous["301x601"]=prior4["local_sampled_peak"]
    out={"schema":"J0740_F105_NATIVE_C_RNS_301x601_LOCAL_FIXED_J_PEAK_PROBE_V1",
      "status":status,"mesh":GRID,"EOS_sha256":EOS_SHA,"target_J_cgs":TARGET_J,
      "J_relative_tolerance":J_REL_TOL,"F103_artifact_sha256":F103_ZIP_SHA,"F104_artifact_sha256":F104_ZIP_SHA,"F104_prior_validated":True,
      "F102_old_28_stars_reused_without_rerun":True,"F103_7_stars_reused_without_rerun":True,
      "new_native_C_stars":rows,"native_C_errors":errors,"slope_Msun_per_1e15g_cm3":slopes.tolist(),
      "local_sampled_peak_index":peak_idx,"local_sampled_peak":peak,
      "local_turn_sign_change":bool(np.any(slopes>0) and np.any(slopes<0)),
      "local_turn_gate":turn,"previous_mesh_peaks":previous,
      "delta_peak_mass_vs_251x501_msun":(peak["M_msun"]-prior_peak["M_msun"]) if peak else None,
      "claim_limit":"Five finite meshes with local density sampling still do not prove a continuum turning point, rotating dynamical eigenmodes, or full seven-original-EOS X-PSI photon Bayes evidence.",
      "new_native_C_call_count":sum(r["native_C_evaluations"] for r in rows),
      "journal_sha256":sha(journal.read_bytes()) if journal.exists() else None}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print("F105_RESULT",json.dumps({"status":status,"new_C_calls":out["new_native_C_call_count"],"peak":peak,"slope":out["slope_Msun_per_1e15g_cm3"]},sort_keys=True),flush=True)
    if status!="FIFTH_MESH_LOCAL_SAMPLED_TURN_PASS":raise SystemExit(2)

if __name__=="__main__":main()
