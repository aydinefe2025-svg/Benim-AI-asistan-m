#!/usr/bin/env python3
"""Approximate F38 likelihood integration along the existing causal APR4 RNS curve.

This is not a native X-PSI photon reanalysis.  It integrates the published-
posterior-derived L/Z surface over the explicitly chosen uniform-central-
energy-density prior on the fixed-spin stable branch.  The result is a
conditional, exploratory evidence ratio and must not be called the final
seven-EOS Bayes result.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.integrate import trapezoid

HERE = Path(__file__).resolve().parent
ROT = HERE.parent / "rotating_gr"
sys.path.insert(0, str(ROT))
import precise_apr4_mass_spin_root as root

SPIN_HZ = 346.536369
ANCHOR_M = 2.073
RADIO_MU = 2.082
RADIO_SIGMA = 0.0703
GRID_RANGES = {"coarse": (1.923, 2.163, 0.010), "fine": (1.923, 2.163, 0.005)}

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def source_surfaces(folder):
    paths=sorted(Path(folder).glob("posterior_prior_ratio_weighted_*.npz"))
    if len(paths)!=3: raise ValueError(f"expected 3 weighted F38 surfaces, found {len(paths)}")
    out=[]
    for p in paths:
        with np.load(p) as z:
            m=np.asarray(z["mass_centres"],float)
            r=np.asarray(z["radius_centres_km"],float)
            q=np.asarray(z["relative_likelihood_L_over_Z"],float)
            mask=np.asarray(z["hard_source_support"],bool)
            sm=float(z["sigma_M_Msun"]); sr=float(z["sigma_R_km"])
        if q.shape!=(m.size,r.size) or mask.shape!=q.shape or not np.isfinite(q).all():
            raise ValueError(f"invalid F38 surface: {p}")
        q=np.where(mask,q,0.)
        out.append({"path":str(p),"sha256":sha(p),"m":m,"r":r,"q":q,
                    "sm":sm,"sr":sr,
                    "interp":RegularGridInterpolator((m,r),q,bounds_error=False,fill_value=0.)})
    return out

def root_curve(binary, eos_table, anchor_json, step):
    j=json.loads(Path(anchor_json).read_text(encoding="utf-8"))
    candidates=[]
    for rec in j.get("results",[]):
        model=rec.get("model",{})
        if rec.get("status")=="PASS" and rec.get("grid")=="rns-candidate-201":
            candidates.append(model)
    if not candidates:
        raise ValueError("cannot find the recorded fine-grid anchor root")
    a=candidates[0]
    ec=float(a.get("central_energy_density_g_cm3",a["central_density_g_cm3"]))/1e15
    seed=(ec,float(a["axis_ratio"]))
    lo,hi,base=GRID_RANGES[step]
    n=round((hi-lo)/base)
    targets=np.linspace(lo,hi,n+1)
    if not np.any(np.isclose(targets,ANCHOR_M,atol=1e-10)):
        raise ValueError("mass grid must contain anchor")
    solved={ANCHOR_M:dict(a)}
    # Continue away from the already verified anchor in each direction.
    for direction in (1,-1):
        seq=targets[targets>ANCHOR_M] if direction==1 else targets[targets<ANCHOR_M][::-1]
        current_seed=seed
        for mt in seq:
            root.TARGET_MASS_MSUN=float(mt)
            ans=root.solve_fixed_mf(lambda e,rr:root.run_model(
                Path(binary),Path(eos_table),e,rr),current_seed)
            ans["target_mass_msun"]=float(mt)
            if abs(ans["mass_msun"]-mt)>root.MASS_TOL_MSUN or abs(ans["spin_hz"]-SPIN_HZ)>root.SPIN_TOL_HZ:
                raise ValueError(f"root tolerance failed at M={mt}")
            solved[float(mt)]=ans
            current_seed=(float(ans["central_energy_density_g_cm3"])/1e15,float(ans["axis_ratio"]))
    rows=[solved[float(m)] for m in targets]
    m=np.asarray([x["mass_msun"] for x in rows])
    ec=np.asarray([x["central_energy_density_g_cm3"] for x in rows])
    rad=np.asarray([x["radius_eq_km"] for x in rows])
    if np.any(np.diff(ec)<=0) or np.any(np.diff(m)<=0):
        raise ValueError("sequence is not a single monotonically rising branch")
    return {"targets":targets,"mass":m,"ec":ec,"radius":rad,"roots":rows}

def evidence(curve, surfaces):
    m=curve["mass"]; ec=curve["ec"]; rad=curve["radius"]
    radio=np.exp(-0.5*((m-RADIO_MU)/RADIO_SIGMA)**2)
    den=trapezoid(radio,ec)
    if not den>0: raise ValueError("zero radio-mass weight on sampled stable branch")
    values={}
    for s in surfaces:
        pts=np.column_stack((m,rad))
        ll=s["interp"](pts)
        num=trapezoid(ll*radio,ec)
        values[f'{s["sm"]:.3f}_{s["sr"]:.2f}']=float(num/den)
    return values

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",required=True); p.add_argument("--eos-table",required=True)
    p.add_argument("--anchor",required=True); p.add_argument("--surfaces",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    surfaces=source_surfaces(a.surfaces)
    curves={k:root_curve(a.binary,a.eos_table,a.anchor,k) for k in GRID_RANGES}
    vals={k:evidence(curves[k],surfaces) for k in curves}
    names=sorted(vals["fine"])
    deltas={n:abs(vals["fine"][n]/vals["coarse"][n]-1) for n in names}
    result={
      "schema":"j0740-apr4-causal-candidate-F38-curve-integral-v1",
      "status":"PASS_APPROXIMATE_CURVE_INTEGRAL_NOT_FINAL_EOS_BAYES",
      "model":"APR4_EPP_LALSuite_7.26.4_NATIVE_CAUSAL_COMPLETION",
      "spin_hz":SPIN_HZ,
      "source":"F38 published-posterior-derived nuisance-marginal relative L/Z surfaces; photon-level X-PSI was not rerun",
      "prior_assumption":"uniform central energy density over sampled monotonically rising fixed-spin sequence; radio Gaussian applied exactly once after dividing it out of source effective prior",
      "radio_mass":{"mu_msun":RADIO_MU,"sigma_msun":RADIO_SIGMA},
      "surface_sha256":{s["path"]:s["sha256"] for s in surfaces},
      "evidence_ratio_L_over_Z_by_bandwidth":vals,
      "coarse_fine_relative_delta":deltas,
      "grid_convergence":"PASS_2_PERCENT" if max(deltas.values())<.02 else "FAIL_OR_NOT_CONVERGED",
      "curves":{k:{"mass_min":float(v["mass"].min()),"mass_max":float(v["mass"].max()),
        "central_energy_density_min_g_cm3":float(v["ec"].min()),"central_energy_density_max_g_cm3":float(v["ec"].max()),
        "radius_min_km":float(v["radius"].min()),"radius_max_km":float(v["radius"].max()),
        "points":len(v["mass"]),"roots":v["roots"]} for k,v in curves.items()},
      "native_compiled_xpsi_photon_reanalysis":"NOT_RUN",
      "full_seven_eos_bayes":"NOT_RUN",
      "absolute_baryon_density_normalization":"NOT_ESTABLISHED",
      "causal_completion_uniqueness":"NOT_ESTABLISHED"}
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"values":vals,
      "grid_convergence":result["grid_convergence"],"deltas":deltas},indent=2))
    if result["grid_convergence"]!="PASS_2_PERCENT": raise SystemExit(2)

if __name__=="__main__": main()
