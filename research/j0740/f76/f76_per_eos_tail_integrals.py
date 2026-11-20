#!/usr/bin/env python3
"""F76: extend F75 posterior-flow integrals over each model's own verified direct-root support.

Scores across EOS are deliberately not ranked: support differs by model, and these
candidate barotropes do not have an accepted EOS prior. No RNS roots are recomputed.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path
import numpy as np
from scipy.integrate import simpson

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "f51"))
sys.path.insert(0, str(ROOT / "f75"))
import f51_extended_support_audit as f51
import f75_prior_corrected_flow_gr_integrals as f75

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20), b""):
            h.update(b)
    return h.hexdigest()

def run(npz_path, nicer_source, archives, f44, f48, out):
    if f75.git_blob_sha(npz_path) != f75.NPZ_BLOB_SHA:
        raise ValueError("F76_JESTER_NPZ_BLOB_DRIFT")
    if f75.git_blob_sha(nicer_source) != f75.NICER_BLOB_SHA:
        raise ValueError("F76_JESTER_LIKELIHOOD_BLOB_DRIFT")
    curves=f51.load_verified_curves(archives, f44, f48)
    with np.load(npz_path, allow_pickle=False) as z:
        mass=np.asarray(z["mass"],float)
        radius=np.asarray(z["radius"],float)
    configs=[(.012,.15),(.018,.25),(.025,.35)]
    result={
      "schema":"A01.01.51_F76_per_EOS_own_direct_root_support_posterior_flow_v1",
      "status":"PER_EOS_DIRECT_ROOT_SUPPORT_INTEGRALS_NOT_COMPARABLE_EOS_EVIDENCE",
      "lineage":{"jester_commit":f75.JESTER_COMMIT,"posterior_samples":len(mass),
        "npz_git_blob_sha1":f75.NPZ_BLOB_SHA,"nicer_py_git_blob_sha1":f75.NICER_BLOB_SHA,
        "native_prior_sha256":f75.PRIOR_SHA256,"maryland_likelihood_multiplied":False,
        "preserved_direct_rns_roots_recomputed":False},
      "method":"For each EOS, integrate target_mass_prior/source_pi_eff times the JESTER source-posterior KDE along every preserved verified direct root from 1.89 Msun to that model's maximum direct-root mass. This reports that model's own support contribution only; differing support forbids cross-model ranking.",
      "per_model_mass_prior_coverage":{},
      "bandwidths":{},
      "limitations":["JESTER posterior KDE approximation, not event-level X-PSI photon likelihood.",
        "F42 causal-lift candidate barotropes, not original nuclear EOS models.",
        "Each EOS has a different maximum directly computed support; values are not comparable as EOS evidence or posterior probabilities.",
        "No EOS prior/model probabilities, global fixed-J stability acceptance, or extrapolation beyond direct roots.",
        "No new RNS stars; F51/F48 direct roots are consumed as archived."],
    }
    for bw_m,bw_r in configs:
        mg,rg,q,interp,diag=f75.build_kde(mass,radius,bw_m,bw_r)
        models={}
        for name,curve in curves.items():
            mm=np.asarray(curve["all_m"],float); rr=np.asarray(curve["all_r"],float)
            pi=f75.source_pi_eff(mm,rr)
            if np.any(pi<=0): raise ValueError("F76_DIRECT_ROOT_OUTSIDE_SOURCE_PRIOR_"+name)
            qline=np.asarray(interp(np.column_stack((mm,rr))),float)
            ratio=f75.mass_pdf(mm)/pi
            raw=float(simpson(ratio*qline,x=mm))
            cov=f51.prior_probability(float(mm[0]),float(mm[-1]))
            common_n=int(np.count_nonzero(mm<=f51.HI+1e-9))
            tail_n=int(np.count_nonzero(mm>f51.HI+1e-9))
            models[name]={
              "direct_root_mass_interval_msun":[float(mm[0]),float(mm[-1])],
              "direct_root_count":len(mm),"roots_above_2p10_msun_count":tail_n,
              "common_1p89_to_2p10_root_count":common_n,
              "radio_mass_prior_coverage_on_own_interval":cov,
              "source_prior_corrected_integral":raw,
              "conditional_on_own_interval":raw/cov,
              "q_line_integral_unweighted":float(simpson(qline,x=mm)),
              "relative_to_largest_own_support_value_NOT_A_MODEL_PROBABILITY":None,
            }
        # This ratio is a plotting aid only. Since each model has a different
        # integration interval it is not an EOS ranking or a probability.
        mx=max(v["source_prior_corrected_integral"] for v in models.values())
        for v in models.values():
            v["relative_to_largest_own_support_value_NOT_A_MODEL_PROBABILITY"]=v["source_prior_corrected_integral"]/mx
        result["bandwidths"][f"mass_bw={bw_m}_radius_bw={bw_r}"]={
          "kde_diagnostic":diag,"models":models,
          "warning":"Ratios compare different mass supports and have no EOS model-probability interpretation."}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    return result

def main():
    p=argparse.ArgumentParser()
    for n in ("npz","nicer_source","f44","f48","curves_dir","out"):
        p.add_argument("--"+n.replace("_","-"),type=Path,required=True)
    a=p.parse_args()
    archives={n:a.curves_dir/("F46_"+n+".zip") for n in f51.EOS}
    r=run(a.npz,a.nicer_source,archives,a.f44,a.f48,a.out)
    print(json.dumps({"status":r["status"],"bandwidths":r["bandwidths"]},indent=2))

if __name__=="__main__": main()
