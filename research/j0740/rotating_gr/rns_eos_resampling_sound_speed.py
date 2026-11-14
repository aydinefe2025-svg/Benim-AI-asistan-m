"""196-point RNS EOS table derivative vs exact JESTER native cs2 at J0740.

Source identity checks reproduce the exact same upstream JESTER NPZ SHA256.
NumPy-generated 196-row RNS TEXT file hashes can differ between runner versions;
this is never silently called a byte-identical reconstruction. Instead compare
the local finite-resolution table derivative against the source-native cs2
with an explicit numeric tolerance, AND retain both file hashes and NumPy version.
Neither calculation is an exact C/RNS interpolation derivative or EOS posterior.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from jester_to_rns import from_jester_npz,write_rns
from center_causality import central_causality

EOS=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
SOURCE_COMMIT="e6768650ce992abfd1153a6833857572fe5cd230"
RNS_JSON_SHA256="d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"
C_CGS=2.99792458e10
MAX_NATIVE_CS2_DISCREPANCY=0.075

def score_numeric_lineage(native_cs2, secant_cs2, local_cs2, archive_sha, regenerated_sha):
    """Keep byte-identity separate from density-local physical sensitivity.

    The tolerance is a transparent screening choice, not a posterior bound.
    A mismatched TEXT SHA is reported as such even when numerical slopes agree.
    """
    vals=(native_cs2,secant_cs2,local_cs2)
    if not all(math.isfinite(float(v)) for v in vals):
        raise ValueError("Nonfinite native/RNS-table sound speed")
    if not (0 <= native_cs2 <= 5 and 0 < secant_cs2 < 5 and 0 < local_cs2 < 5):
        raise ValueError("Nonphysical native/RNS-table center sound speed")
    max_diff=max(abs(secant_cs2-native_cs2),abs(local_cs2-native_cs2))
    if max_diff>MAX_NATIVE_CS2_DISCREPANCY:
        raise ValueError(f"Source-native and regenerated RNS table sound speed diverged by {max_diff:.6g}")
    return {"original_table_text_sha256":archive_sha,
            "regenerated_table_text_sha256":regenerated_sha,
            "original_vs_regenerated_table_bytes_match":archive_sha==regenerated_sha,
            "source_native_center_cs2_over_c2":native_cs2,
            "source_vs_table_max_abs_cs2_deviation":max_diff,
            "numeric_comparison_tolerance_cs2":MAX_NATIVE_CS2_DISCREPANCY,
            "classification":"SOURCE_VERIFIED_NUMERIC_SLOPE_AGREEMENT_NOT_BYTE_IDENTITY_PROOF"}



def eos_table_slopes(rows:np.ndarray, center_rho:float)->dict:
    rows=np.asarray(rows,dtype=float)
    if (rows.ndim!=2 or rows.shape[1]!=4 or len(rows)<30 or len(rows)>200
            or not np.all(np.isfinite(rows)) or np.any(rows<=0)
            or np.any(np.diff(rows[:,0])<=0) or np.any(np.diff(rows[:,1])<=0)
            or not math.isfinite(center_rho) or center_rho<=0):
        raise ValueError("Invalid RNS thermodynamic table or center")
    rho,p=rows[:,0],rows[:,1]
    if not rho[0]<=center_rho<=rho[-1]:
        raise ValueError("center outside exact RNS table support")
    i=min(max(0,int(np.searchsorted(rho,center_rho,side="right")-1)),len(rho)-2)
    a,b=float(rho[i]),float(rho[i+1])
    p0,p1=float(p[i]),float(p[i+1])
    cs2_secant=(p1-p0)/((b-a)*C_CGS**2)
    gamma=(math.log(p1)-math.log(p0))/(math.log(b)-math.log(a))
    p_center=math.exp(math.log(p0)+gamma*(math.log(center_rho)-math.log(a)))
    cs2_local_powerlaw=gamma*p_center/(center_rho*C_CGS**2)
    return {"rho_bracket_g_cm3":[a,b],
            "p_bracket_dyn_cm2":[p0,p1],
            "bracket_index":i,
            "center_rho_g_cm3":float(center_rho),
            "local_logP_logRho_gamma":gamma,
            "table_secant_dp_de":cs2_secant,
            "table_local_powerlaw_dp_de":cs2_local_powerlaw,
            "rns_table_density_monotone":True,
            "rns_table_pressure_monotone":True,
            "warning":"These two finite-resolution slopes are sensitivity proxies, not an exact C/RNS interpolation derivative."}


def audit(rns,source_dir:Path,workdir:Path):
    if (rns.get("status")!="ALL_SEVEN_VALIDATED"
            or rns.get("validated_eos_count")!=7
            or set(rns.get("eos",{}))!=set(EOS)
            or rns.get("jester_upstream_commit")!=SOURCE_COMMIT):
        raise ValueError("Pinned successful RNS 7-EOS identity check failed")
    out={}
    for name in EOS:
        model=rns["eos"][name]
        if model.get("status")!="MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED":
            raise ValueError(f"{name}: source RNS model not validated")
        src=source_dir/(name+".npz")
        srcsha=hashlib.sha256(src.read_bytes()).hexdigest()
        if model["source_npz_sha256"]!=srcsha:raise ValueError(f"{name}: source NPZ mismatch")
        rows,info=from_jester_npz(src,points=196)
        if info["source_npz_sha256"]!=srcsha:raise ValueError("Source SHA check failed")
        dst=workdir/(name+".rns")
        write_rns(dst,rows)
        table_sha=hashlib.sha256(dst.read_bytes()).hexdigest()
        rho=float(model["rns_rotating_at_target"]["central_energy_density_g_cm3"])
        vals=eos_table_slopes(rows,rho)
        with np.load(src,allow_pickle=False) as native_source:
            original=central_causality(native_source["e"],native_source["p"],
                                      native_source["cs2"],rho)
        diag=score_numeric_lineage(
            original["cs2_over_c2_interpolated_linear_energy"],
            vals["table_secant_dp_de"],vals["table_local_powerlaw_dp_de"],
            model["rns_table_sha256"],table_sha)
        vals.update(diag)
        vals.update({"eos":name,"source_npz_sha256":srcsha,
                     "regenerated_RNS_196pt_table_sha256":table_sha,
                     "numpy_version":np.__version__,
                     "rns_center_mass_msun":float(model["rns_rotating_at_target"]["mass_msun"]),
                     "rns_center_spin_hz_reported":float(model["rns_rotating_at_target"]["spin_hz_reported"]),
                     "source_table_points":info["source_points"],
                     "rns_table_points":info["output_points"]})
        out[name]=vals
    return {"schema":"j0740-seven-RNS-source-verified-table-cs2-sensitivity-v2",
            "status":"SEVEN_SOURCE_MATCHED_NUMERIC_CS2_SENSITIVITY_PASS_NOT_BYTE_PROOF",
            "byte_equal_table_count":sum(int(x["original_vs_regenerated_table_bytes_match"])
                                          for x in out.values()),
            "byte_unequal_table_count":sum(int(not x["original_vs_regenerated_table_bytes_match"])
                                            for x in out.values()),
            "source_commit":SOURCE_COMMIT,"pinned_rns_workflow_run":42353019033,
            "pinned_rns_json_sha256":RNS_JSON_SHA256,
            "interpretation":"Independent regenerated RNS 196-node TABLE numeric slopes compared to pinned JESTER source-native cs2. Some generated text SHA differ: not the same exact bytes as the historical C solver input. This is not continuous C solver derivative, causality proof, or EOS posterior.",
            "eos":out}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rns-json",type=Path,required=True)
    p.add_argument("--jester-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    raw=a.rns_json.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=RNS_JSON_SHA256:
        raise ValueError("Pinned RNS artifact JSON SHA mismatch")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    evidence=audit(json.loads(raw),a.jester_dir,a.out.parent)
    a.out.write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n")
    for n,r in evidence["eos"].items():
        print(n,"same_table_BYTES",r["original_vs_regenerated_table_bytes_match"],
              "native_cs2",r["source_native_center_cs2_over_c2"],
              "secant",r["table_secant_dp_de"],
              "powerlaw",r["table_local_powerlaw_dp_de"],flush=True)


if __name__=="__main__":main()
