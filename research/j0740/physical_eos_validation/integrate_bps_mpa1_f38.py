#!/usr/bin/env python3
"""Partial F38 source-prior-corrected integral for the direct BPS-MPA1 RNS curve.

This is explicitly not photon-level X-PSI or a final EOS Bayes factor. It
integrates only the directly solved mass window and leaves the omitted tails
uncomputed rather than setting them to zero.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.stats import truncnorm

M_MU,M_SIG=2.082,0.0703
M_MIN,M_MAX=M_MU-5*M_SIG,M_MU+5*M_SIG
MASS_WINDOW=(1.89,2.175)
BANDWIDTHS=(("0.015_0.20",.015,.20),("0.025_0.35",.025,.35),("0.040_0.50",.040,.50))
N_GRID=(5001,10001,20001)
EXPECTED_POSTERIOR_SHA="1549467c64a8801c39213bd28c89737d087cc5ab7a70da1d8d3a32b2d09185c8"

def sha256_bytes(b): return hashlib.sha256(b).hexdigest()

def bilinear(mg,rg,v,support,m,r):
    i=np.clip(np.searchsorted(mg,m,side="right")-1,0,len(mg)-2)
    j=np.clip(np.searchsorted(rg,r,side="right")-1,0,len(rg)-2)
    tm=(m-mg[i])/(mg[i+1]-mg[i]); tr=(r-rg[j])/(rg[j+1]-rg[j])
    ok=support[i,j]&support[i+1,j]&support[i,j+1]&support[i+1,j+1]
    if not np.all(ok):
        bad=int(np.count_nonzero(~ok))
        raise ValueError(f"curve crosses {bad} cells outside hard F38 source support")
    return ((1-tm)*(1-tr)*v[i,j]+tm*(1-tr)*v[i+1,j]+
            (1-tm)*tr*v[i,j+1]+tm*tr*v[i+1,j+1])

def verify_f38(folder):
    folder=Path(folder)
    mf=json.loads((folder/"SHA256_manifest.json").read_text())
    checked={}
    for name,record in mf.items():
        p=folder/name
        b=p.read_bytes()
        expected=record["sha256"] if isinstance(record,dict) else record
        if sha256_bytes(b)!=expected: raise ValueError(f"F38 SHA mismatch: {name}")
        if isinstance(record,dict) and len(b)!=record["bytes"]: raise ValueError(f"F38 byte count mismatch: {name}")
        checked[name]={"bytes":len(b),"sha256":expected}
    report=json.loads((folder/"source_likelihood_report.json").read_text())
    if report["original_posterior_sha256"]!=EXPECTED_POSTERIOR_SHA: raise ValueError("Salmi source posterior SHA mismatch")
    if not report.get("source_prior_includes_radio_mass_gaussian"): raise ValueError("source effective prior does not identify radio-mass factor")
    if not str(report.get("status","")).startswith("PASS_APPROXIMATE_"): raise ValueError("F38 source likelihood status not accepted")
    return report,checked

def selftest():
    mg=np.array([0.,1.]); rg=np.array([0.,1.]); v=np.array([[1.,2.],[3.,4.]])
    sup=np.ones((2,2),bool)
    got=bilinear(mg,rg,v,sup,np.array([.5]),np.array([.5]))
    assert abs(got[0]-2.5)<1e-14
    sup[0,0]=False
    try: bilinear(mg,rg,v,sup,np.array([.5]),np.array([.5]))
    except ValueError: pass
    else: raise AssertionError("hard source support must fail closed")
    q=truncnorm.pdf(np.linspace(M_MIN,M_MAX,20001),-5,5,loc=M_MU,scale=M_SIG)
    assert abs(np.trapezoid(q,np.linspace(M_MIN,M_MAX,20001))-1)<2e-6
    coverage=float(truncnorm.cdf(MASS_WINDOW[1],-5,5,loc=M_MU,scale=M_SIG)-
                   truncnorm.cdf(MASS_WINDOW[0],-5,5,loc=M_MU,scale=M_SIG))
    assert .90<coverage<.91
    print("PASS: bilinear interpolation, fail-closed source boundary, normalized prior, and window coverage")

def run(curve_path,f38_dir):
    curve=json.loads(Path(curve_path).read_text())
    if curve.get("status")!="PASS_TWO_GRID_CURVE": raise ValueError("two-grid direct RNS curve did not pass")
    fine=next(x for x in curve["runs"] if x["grid"]=="201x401")
    points=sorted((x["result"] for x in fine["points"]),key=lambda x:x["M_msun"])
    masses=np.array([x["M_msun"] for x in points],float)
    radii=np.array([x["R_equatorial_km"] for x in points],float)
    if np.any(np.diff(masses)<=0): raise ValueError("fine-grid RNS mass curve is not strictly increasing")
    if abs(masses[0]-MASS_WINDOW[0])>2e-5 or abs(masses[-1]-MASS_WINDOW[1])>2e-5:
        raise ValueError("direct RNS curve endpoints do not match the declared integration window")
    radius_of_mass=PchipInterpolator(masses,radii,extrapolate=False)
    report,checked=verify_f38(f38_dir)
    results={}; all_quadrature={}
    for kind in ("weighted","resampled"):
      for key,_,_ in BANDWIDTHS:
        name=f"posterior_prior_ratio_{kind}_{key}.npz"
        z=np.load(Path(f38_dir)/name,allow_pickle=False)
        mg=z["mass_centres"].astype(float); rg=z["radius_centres_km"].astype(float)
        vals=z["relative_likelihood_L_over_Z"].astype(float)
        support=z["hard_source_support"].astype(bool)
        if vals.shape!=support.shape or vals.shape!=(len(mg),len(rg)): raise ValueError(f"bad F38 grid: {name}")
        result=[]
        for n in N_GRID:
            m=np.linspace(MASS_WINDOW[0],MASS_WINDOW[1],n)
            r=np.asarray(radius_of_mass(m),float)
            l=bilinear(mg,rg,vals,support,m,r)
            q=truncnorm.pdf(m,-5,5,loc=M_MU,scale=M_SIG)
            value=float(np.trapezoid(q*l,m))
            result.append({"n":n,"partial_prior_weighted_integral":value})
        fine_value=result[-1]["partial_prior_weighted_integral"]
        for x in result: x["abs_delta_to_fine"]=abs(x["partial_prior_weighted_integral"]-fine_value)
        results[f"{kind}_{key}"]={"grid_sha256":checked[name]["sha256"],"quadrature":result}
        all_quadrature[f"{kind}_{key}"]=fine_value
        z.close()
    coverage=float(truncnorm.cdf(MASS_WINDOW[1],-5,5,loc=M_MU,scale=M_SIG)-
                   truncnorm.cdf(MASS_WINDOW[0],-5,5,loc=M_MU,scale=M_SIG))
    wr={}
    bwspread=[]
    for key,_,_ in BANDWIDTHS:
        a=all_quadrature[f"weighted_{key}"]; b=all_quadrature[f"resampled_{key}"]
        wr[key]={"weighted":a,"resampled":b,"relative_difference_percent":100*abs(a-b)/max(abs(a),abs(b),1e-300)}
        bwspread.append(a)
    return {"schema":"J0740_BPS_MPA1_PARTIAL_F38_INTEGRAL_V1",
      "status":"PASS_PARTIAL_APPROXIMATE_SOURCE_PRIOR_CORRECTED_CURVE_INTEGRAL",
      "model":curve["model"],"curve_run_id":curve.get("workflow_run_id"),
      "direct_rns_grid":"201x401","direct_curve_masses_msun":masses.tolist(),
      "direct_curve_radii_equatorial_km":radii.tolist(),
      "mass_prior":{"distribution":"TruncNormal(2.082,0.0703^2; +/-5 sigma), applied once",
        "integration_window_msun":list(MASS_WINDOW),"prior_mass_fraction_in_window":coverage,
        "uncovered_tail_fraction":1-coverage,"tail_likelihood":"NOT_COMPUTED; no zero-tail assumption"},
      "F38":{"source_prior_weighted_resampled_status":report["status"],
        "source_native_XPSI_reanalysis":"NOT_RUN","original_Salmi_posterior_sha256":EXPECTED_POSTERIOR_SHA,
        "verified_files":checked},
      "conditional_partial_integrals":results,
      "weighted_vs_resampled":wr,
      "systematics":{"weighted_KDE_bandwidth_spread_percent":100*(max(bwspread)-min(bwspread))/max(np.mean(bwspread),1e-300)},
      "limits":{"full_EOS_evidence":"NOT_ESTABLISHED","EOS_family_prior":"NOT_DEFINED",
        "full_radio_prior_integral":"NOT_ESTABLISHED; mass tails remain unintegrated",
        "native_XPSI_photon_and_nuisance_inference":"NOT_RUN",
        "physical_acceptance_of_model":"NOT_ESTABLISHED",
        "same_NICER_XMM_photons_multiplied_twice":False}}

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selftest",action="store_true"); p.add_argument("--curve",type=Path); p.add_argument("--f38-dir",type=Path); p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.selftest: selftest()
    else:
        if not(a.curve and a.f38_dir and a.output): p.error("--curve, --f38-dir and --output are required")
        r=run(a.curve,a.f38_dir); a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(r,indent=2,sort_keys=True,allow_nan=False)+"\n")
        print(json.dumps({"status":r["status"],"window_prior_mass_fraction":r["mass_prior"]["prior_mass_fraction_in_window"],"weighted_vs_resampled":r["weighted_vs_resampled"]},sort_keys=True))
