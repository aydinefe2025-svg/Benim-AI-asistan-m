"""Source-matched rotational-center causality audit on pinned JESTER NPZ.

RNS model results are an immutable GitHub Actions artifact, not refitted here.
The physics tests use native JESTER analytic cs2 (dimensionless c_s^2/c^2);
DO NOT infer physical EOS Bayes probabilities or suppress negative cs2 nodes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np

C=299792458.0
G=6.67430e-11
CONVERT=C*C/G*1e-3
EOS=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
SOURCE_COMMIT="e6768650ce992abfd1153a6833857572fe5cd230"
RNS_JSON_SHA256="d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"
RNS_RUN=42353019033
RNS_ARTIFACT=13566144811


def central_causality(e, p, cs2, center_rho):
    e,p,cs2=map(lambda x:np.asarray(x,dtype=float),(e,p,cs2))
    if (e.ndim!=1 or len(e)<100 or p.shape!=e.shape or cs2.shape!=e.shape
            or not all(np.all(np.isfinite(x)) for x in (e,p,cs2))
            or np.any(e<=0) or np.any(p<=0) or np.any(np.diff(p)<=0)
            or not math.isfinite(center_rho) or center_rho<=0):
        raise ValueError("Invalid source EOS or RNS central density")
    rho=e*CONVERT
    # JESTER e may reverse only at low-energy crust transition. The local
    # high-density branch must increase strictly in source ordering.
    decreases=np.flatnonzero(np.diff(rho)<=0)
    start=int(decreases[-1]+1) if len(decreases) else 0
    high=rho[start:]
    if len(high)<10 or np.any(np.diff(high)<=0):
        raise ValueError("No strictly increasing high-density EOS branch")
    if not (high[0]<=center_rho<=high[-1]):
        raise ValueError("RNS central density outside valid source high-density branch")
    pos=int(np.searchsorted(high,center_rho,side="right")-1)
    pos=min(pos,len(high)-2)+start
    frac=(center_rho-rho[pos])/(rho[pos+1]-rho[pos])
    if not 0<=frac<=1:
        raise ValueError("Density interpolation would extrapolate")
    cs_lin=float(cs2[pos]+frac*(cs2[pos+1]-cs2[pos]))
    frac_log=(np.log(center_rho)-np.log(rho[pos]))/(np.log(rho[pos+1])-np.log(rho[pos]))
    cs_log=float(cs2[pos]+frac_log*(cs2[pos+1]-cs2[pos]))
    neg=np.flatnonzero(cs2<0)
    supra=np.flatnonzero(cs2>1+1e-8)
    interior_supra=supra[rho[supra]<=center_rho]
    interior_neg=neg[rho[neg]<=center_rho]
    if len(interior_supra):
        classification="SUPERLUMINAL_NATIVE_SOURCE_NODES_WITHIN_ROTATING_STAR"
    elif len(interior_neg):
        classification="NO_SUPERLUMINAL_NODES_THROUGH_CENTER_BUT_NEGATIVE_CS2_SOURCE"
    else:
        classification="NO_NEGATIVE_OR_SUPERLUMINAL_SOURCE_NODES_THROUGH_CENTER"
    first= int(supra[0]) if len(supra) else None
    crossover=None
    if first is not None and first>0 and cs2[first-1]<1<cs2[first] and rho[first]>rho[first-1]:
        w=(1-cs2[first-1])/(cs2[first]-cs2[first-1])
        crossover=float(rho[first-1]+w*(rho[first]-rho[first-1]))
    return {
      "rotating_center_density_g_cm3":float(center_rho),
      "cs2_over_c2_interpolated_linear_energy":cs_lin,
      "cs2_over_c2_interpolated_log_energy":cs_log,
      "center_interpolation_spread":abs(cs_lin-cs_log),
      "source_cs2_bracketing_indices":[int(pos),int(pos+1)],
      "source_cs2_bracketing_values":[float(cs2[pos]),float(cs2[pos+1])],
      "source_cs2_bracketing_density_g_cm3":[float(rho[pos]),float(rho[pos+1])],
      "first_native_superluminal_density_g_cm3":float(rho[first]) if first is not None else None,
      "first_cs2_one_linear_crossing_estimate_g_cm3":crossover,
      "source_negative_node_count":int(len(neg)),
      "negative_source_node_indices":[int(i) for i in neg[:10]],
      "negative_source_node_density_g_cm3":[float(rho[i]) for i in neg[:10]],
      "negative_source_node_cs2":[float(cs2[i]) for i in neg[:10]],
      "source_nonmonotone_energy_prefix_final_index":start,
      "native_superluminal_nodes_below_center":int(len(interior_supra)),
      "native_negative_nodes_below_center":int(len(interior_neg)),
      "source_max_cs2_below_center":float(np.max(cs2[rho<=center_rho])),
      "classification":classification,
      "warning":"Point-sampled native analytic cs2, not continuous causality proof; negative low-density nodes may reflect EOS crust behavior or interpolation artifact.",
    }


def audit(rns, source_dir):
    if (rns.get("status")!="ALL_SEVEN_VALIDATED" or rns.get("validated_eos_count")!=7
            or rns.get("jester_upstream_commit")!=SOURCE_COMMIT
            or not abs(rns.get("spin_hz",0)-346.536369)<1e-6
            or set(rns.get("eos",{}))!=set(EOS)):
        raise ValueError("RNS 7/7 source identity, spin, or EOS set mismatch")
    rows={}
    for name in EOS:
        model=rns["eos"][name]
        if model["status"]!="MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED":
            raise ValueError(f"RNS {name} not validated")
        path=source_dir/(name+".npz")
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=model["source_npz_sha256"]:
            raise ValueError(f"{name} source-NPZ SHA256 mismatch")
        with np.load(path,allow_pickle=False) as data:
            e,p,cs2=data["e"],data["p"],data["cs2"]
        center=float(model["rns_rotating_at_target"]["central_energy_density_g_cm3"])
        out=central_causality(e,p,cs2,center)
        out["rns_rotating_eq_radius_km"]=float(model["rns_rotating_at_target"]["radius_eq_km"])
        out["source_npz_sha256"]=digest
        out["source_eos"]=name
        rows[name]=out
    return {
      "schema":"j0740-native-cs2-at-rotating-center-v1",
      "status":"SEVEN_EOS_SOURCE_MATCHED_CAUSALITY_DIAGNOSTIC_COMPLETE_NOT_BAYES",
      "rns_workflow_run":RNS_RUN,
      "rns_artifact_id":RNS_ARTIFACT,
      "rns_json_sha256":RNS_JSON_SHA256,
      "jester_commit":SOURCE_COMMIT,
      "eos":rows,
      "method":"linear e and log(e) interpolation on strict monotone high-density source EOS segment; negative crust nodes retained and flagged",
      "limitation":"Not X-PSI marginalized photon likelihood, not EOS model probabilities, not formal rotating-star stability proof",
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rns-json",required=True,type=Path)
    parser.add_argument("--jester-dir",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args()
    data=args.rns_json.read_bytes()
    if hashlib.sha256(data).hexdigest()!=RNS_JSON_SHA256:
        raise ValueError("Pinned 7EOS RNS JSON SHA256 mismatch")
    output=audit(json.loads(data),args.jester_dir)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    for name,row in output["eos"].items():
        print(name, "cs2_center",f"{row['cs2_over_c2_interpolated_linear_energy']:.6f}",
              "classification",row["classification"],
              "negative_nodes",row["source_negative_node_count"],flush=True)


if __name__=="__main__":
    main()
