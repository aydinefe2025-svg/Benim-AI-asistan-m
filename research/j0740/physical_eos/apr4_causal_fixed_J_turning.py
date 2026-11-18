"""F37: independent fixed-J turning-point gate for the *new* causal APR4 completion.
Uses the already verified F36 RNS model as the angular-momentum J anchor.
Reports a fixed-J mass-sequence turning point only if numerically bracketed;
not a proof of nonlinear/dynamical stability or a seven-EOS Bayes result.
"""
from __future__ import annotations
import argparse, hashlib, json, math, re, subprocess, sys
from pathlib import Path
import numpy as np
from scipy.optimize import brentq, minimize_scalar

GR_REF={"rho_c":1759348661510506.5,"axis_ratio":0.9861881190400344,
        "M_msun":2.073000000019222,"spin_hz":346.5363691494884,
        "R_eq_km":10.782043513931155}
MODEL="APR4_EPP_LALSuite_7.26.4_NATIVE_CAUSAL_COMPLETION"
PINNED_SOURCE_RNS="97e85d325a33e37f702306414533f6cd77812477"
PINNED_EOS_SHA="623be1716201463c775e8bfc4b560f4646ecbbac14ba30335599ea38311e4a19"
ROOT_F36_SHA="d7e59a07142da2f4227ba0d0fd8f6610fd11487ec741e3f96833f42738b33fc0"
DENSITY_SEQUENCE_E15=[1.45,1.60,1.70,1.7593486615105065,1.90,2.05,2.20,2.35,2.50,2.60,2.70,2.80,2.90,3.00,3.15,3.30,3.45]
CANDIDATE_RATIOS=(1.0,.995,.990,.985,.980,.970,.955,.94,.92,.90)
# Constant normalization maps the existing m_avg first-law n table to LAL's
# standard m_u convention; fixed-J turning depends on M,J and is unchanged.
BARYON_MASS_UNIT_KG=1.66053906660e-27
NUMBER_DENSITY_SCALE_MAVG_TO_MU=1.0079706912840662

def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def patch_rns_source(src):
    # Same pinned input printf as F36, BUT add star.ang_mom (cgs) as SIXTH field.
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"rotating_gr"))
    from precise_apr4_mass_spin_root import _OUTPUT_RE
    source=Path(src)
    old=source.read_text(encoding="utf8")
    new_stmt=('printf("%.17g %.17g %.17g %.17g %.17g %.17g\\n",'
              'star.e_center,star.Mass/MSUN,star.R_e*1e-5,'
              'star.Omega/(2.0*PI),star.Mass_0/MSUN,star.ang_mom);')
    changed,n=_OUTPUT_RE.subn(lambda _:new_stmt,old)
    if n!=1:raise ValueError(f"pinned RNS source printf mismatch: {n}")
    source.write_text(changed,encoding="utf8",newline="\n")
    return {"orig_sha256":hashlib.sha256(old.encode()).hexdigest(),
            "patched_sha256":sha256(source),"replacements":n,
            "printed_J_cgs_symbol":"star.ang_mom",
            "scope":"printf diagnostic only: no C solver arithmetic touched"}

def parse_model(text):
    vals=[]
    for line in text.splitlines():
        xs=line.split()
        if len(xs)!=6:continue
        try: row=[float(x) for x in xs]
        except ValueError:continue
        if all(math.isfinite(x) for x in row):vals.append(row)
    if len(vals)!=1:raise ValueError(f"Expected one 6-float RNS row: got {len(vals)}")
    density,mass,radius,spin,m0,J=vals[0]
    if not(0.0<mass<4 and 6<radius<25 and 0<=spin<2000 and m0>0 and 0<=J<1e53):
        raise ValueError("RNS model bounds failed")
    return {"density_e15":density,"mass_msun":mass,"radius_eq_km":radius,
            "spin_hz":spin,"rns_M0_msun_NOT_PHYSICAL":m0,"J_cgs":J}

def run_one(binary,table,ec,ratio):
    result=subprocess.run([str(Path(binary).resolve()),"-f","./"+Path(table).name,
                           "-e",f"{ec:.12g}","-r",f"{ratio:.10f}"],
                          cwd=Path(table).parent,capture_output=True,text=True,timeout=130)
    if result.returncode:raise RuntimeError("RNS native C exit "+str(result.returncode)
                                            +": "+result.stderr[-400:])
    out=parse_model(result.stdout)
    if abs(out["density_e15"]-ec/1e15)>2e-7:
        raise ValueError("RNS e_c echo mismatched input")
    out["ec_g_cm3"]=ec;out["axis_ratio"]=ratio
    return out

def hold_fixed_J(binary,table,ec,targetJ,trace):
    # bracket by a monotone scan of *real RNS models*; never extrapolate J.
    prev=None;bracket=None;cache={}
    for ratio in CANDIDATE_RATIOS:
        try:
            v=run_one(binary,table,ec,ratio)
            trace.append({"phase":"scan","ratio":ratio,"J_cgs":v["J_cgs"],"status":"OK"})
            cache[ratio]=v
        except Exception as ex:
            trace.append({"phase":"scan","ratio":ratio,"status":"FAILED",
                          "error":type(ex).__name__+": "+str(ex)[:160]})
            continue
        if prev is not None and (prev["J_cgs"]-targetJ)*(v["J_cgs"]-targetJ)<=0:
            bracket=(prev["axis_ratio"],ratio);break
        prev=v
    if bracket is None:raise ValueError("No valid native-RNS fixed-J bracket")
    calls=[0]
    def fn(ratio):
        calls[0]+=1
        out=run_one(binary,table,ec,ratio)
        cache[ratio]=out
        return out["J_cgs"]/targetJ-1.
    low,high=sorted(bracket)
    ratio=float(brentq(fn,low,high,xtol=1e-9,rtol=1e-10,maxiter=45))
    final=cache.get(ratio)
    if final is None:final=run_one(binary,table,ec,ratio)
    residual=abs(final["J_cgs"]/targetJ-1)
    if residual>5e-6:raise ValueError("Fixed-J residual too large")
    final.update({"J_relative_residual":residual,"rns_root_calls":calls[0]})
    return final

def run(sequence_out,table,binary,patch_record):
    assert sha256(table)==PINNED_EOS_SHA, "F36 196-node native causal EOS table hash drift"
    rec={"schema":"j0740-apr4-causal-rotating-constant-J-v1",
         "status":"IN_PROGRESS",
         "model":MODEL,
         "from_F36_root_json_sha256":ROOT_F36_SHA,
         "rns_upstream_commit":PINNED_SOURCE_RNS,
         "table_sha256":sha256(table),
         "binary_sha256":sha256(binary),
         "baryon_density_convention":{"target":"LAL standard atomic mass unit","m_u_kg":BARYON_MASS_UNIT_KG,"scale_from_existing_m_avg_firstlaw_number_density":NUMBER_DENSITY_SCALE_MAVG_TO_MU,"fixed_J_turning_uses_gravitational_M_and_direct_J":"constant n normalization does not alter the M(J=constant) sequence","RNS_M0":"NOT_REINTERPRETED_OR_CLAIMED_PHYSICAL"},
         "patch_record":patch_record,
         "reference_F36":GR_REF,
         "sequence":[],"limitations":["Microphysical surface mu0 not independently measured; conventional m_u normalization is fixed; RNS M0 remains uninterpreted","True nonlinear/dynamical stability not measured",
                                       "Final source XPSI 15D Bayes NOT_RUN"]}
    out=Path(sequence_out);out.parent.mkdir(parents=True,exist_ok=True)
    def save():
        out.write_text(json.dumps(rec,sort_keys=True,indent=2)+"\n",encoding="utf8")
    save()
    try:
        ref=run_one(binary,table,GR_REF["rho_c"],GR_REF["axis_ratio"])
        if abs(ref["mass_msun"]-GR_REF["M_msun"])>1e-5 or abs(ref["spin_hz"]-GR_REF["spin_hz"])>1e-3:
            raise ValueError("F36 reference real-RNS model failed regeneration")
        targetJ=ref["J_cgs"]
        if not 1e44<targetJ<1e52:raise ValueError("Unreasonable J target")
        rec["reference_J_cgs"]=targetJ
        rec["reference_regeneration"]=ref;save()
        for density_e15 in DENSITY_SEQUENCE_E15:
            ec=float(density_e15)*1e15
            trace=[]
            entry={"ec_g_cm3":ec,"trace":trace}
            try:
                result=hold_fixed_J(binary,table,ec,targetJ,trace)
                entry.update(result);entry["status"]="PASS_FIXED_J"
            except Exception as e:
                entry.update({"status":"FAILED_FIXED_J","reason":type(e).__name__+": "+str(e)})
            rec["sequence"].append(entry);save()
            print(json.dumps({"ec":ec,"status":entry["status"],
                              "mass":entry.get("mass_msun"),"J_error":entry.get("J_relative_residual")}),
                  flush=True)
        good=[x for x in rec["sequence"] if x["status"]=="PASS_FIXED_J"]
        if len(good)<8:raise ValueError("Fewer than 8 converged fixed-J stars")
        a=sorted(good,key=lambda x:x["ec_g_cm3"])
        masses=[x["mass_msun"] for x in a]
        ip=max(range(len(a)),key=lambda i:masses[i])
        if not 2<=ip<=len(a)-3:
            rec["status"]="UNBRACKETED_TURNING_POINT_NO_STABILITY_CLAIM"
        elif not (masses[ip]>masses[ip-1] and masses[ip]>masses[ip+1]):
            rec["status"]="NONMONOTONE_OR_DEGENERATE_NO_STABILITY_CLAIM"
        else:
            rec["bracketed_mass_maximum"]={"central_density_bracket_g_cm3":
                [a[ip-1]["ec_g_cm3"],a[ip+1]["ec_g_cm3"]],
                "sampled_peak_ec_g_cm3":a[ip]["ec_g_cm3"],
                "sampled_mass_msun":masses[ip],
                "sampled_radius_eq_km":a[ip]["radius_eq_km"]}
            rec["status"]="PASS_SAMPLED_CONSTANT_J_TURNING_BRACKET_NOT_DYNAMICAL_CERTIFICATION"
    except Exception as exc:
        rec["error"]=type(exc).__name__+": "+str(exc)
        rec["status"]="FAIL_OR_INCOMPLETE_FIXED_J"
        save()
        raise
    save()
    return rec

def selftest():
    sample="junk\\n1.75934866 2.073 10.782 346.536 2.45 2.0e48\\n"
    ans=parse_model(sample.replace("\\n","\n"))
    assert ans["J_cgs"]==2e48 and ans["mass_msun"]==2.073
    try:parse_model("0 0 0 0 0 0")
    except ValueError:pass
    else:raise AssertionError("bad model not rejected")
    assert len(DENSITY_SEQUENCE_E15)>=14 and min(DENSITY_SEQUENCE_E15)<1.7593
    print("F37_SELFTEST_PASS: six-field J parser / source bound / density sweep")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=["selftest","patch","run"],required=True)
    p.add_argument("--source",type=Path)
    p.add_argument("--table",type=Path)
    p.add_argument("--binary",type=Path)
    p.add_argument("--out",type=Path)
    p.add_argument("--patch-report",type=Path)
    v=p.parse_args()
    if v.mode=="selftest":return selftest()
    if v.mode=="patch":
        x=patch_rns_source(v.source)
        v.out.parent.mkdir(parents=True,exist_ok=True)
        v.out.write_text(json.dumps(x,sort_keys=True,indent=2),encoding="utf8")
        return print(json.dumps(x))
    patch=json.loads(v.patch_report.read_text(encoding="utf8"))
    outcome=run(v.out,v.table,v.binary,patch)
    print(json.dumps({"status":outcome["status"],
                      "reference_J_cgs":outcome.get("reference_J_cgs"),
                      "successful":sum(x["status"]=="PASS_FIXED_J" for x in outcome["sequence"]),
                      "bracket":outcome.get("bracketed_mass_maximum")},indent=2))
    if not outcome["status"].startswith("PASS"):
        raise SystemExit(2)

if __name__=="__main__":main()