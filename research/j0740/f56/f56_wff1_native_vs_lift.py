"""F56: Source-native JESTER WFF1 vs NEW F42 causal-lift+cold-gas EOS.

Exact SHA-pinned original NPZ, F44 original C-RNS tabulation, F53 genuine
201x401 reference star. Compare pressure-aligned energy, causal secants,
analytic first-law enthalpy/baryon *under explicit cold gas assumption*, and
source modification near F53 reference core density.

This is an input-physics provenance diagnostic, NOT a new RNS C calculation,
nor physical validation of F42/WFF1, nor native X-PSI/Bayesian evidence.
Do not call pressure-matched central density a source-native star solution.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,sys,zipfile
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"f42"))
from f42_causal_firstlaw_candidates import Candidate,C,G,MB

NPZ_SHA="119b8a25435faeddf00f5d3638f3ff2ff00283ce60caacc24cc37c6e2e030ed3"
F44_SHA="b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98"
F53_SHA="e35a52b02745d596cdea93427e15d5f7eb1e52c6f591fb21eb61501d57de2ae7"
JESTER_COMMIT="e6768650ce992abfd1153a6833857572fe5cd230"
TARGET_EC_CGS=2.9e15
TABLE_REL_TOL=2e-12

def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle,"sha256").hexdigest()

def source_thermo(p,e,alpha=.6):
    """Raw e(p), no energy lift. Same hypothetical cold-gas extrapolation."""
    p,e=np.asarray(p,float),np.asarray(e,float)
    if not (p.ndim==1 and p.shape==e.shape and len(p)>10
            and np.isfinite(p).all() and np.isfinite(e).all()
            and np.all(p>0) and np.all(e>0) and
            np.all(np.diff(p)>0) and np.all(np.diff(e)>0)):
        raise ValueError("UNMODIFIED_SOURCE_NONMONOTONIC_OR_NONFINITE")
    dp=np.diff(p);de=np.diff(e); slopes=de/dp
    source_cs2=dp/de
    h=np.empty(len(p),float)
    h[0]=math.log1p(p[0]/e[0])/(1-alpha)
    for i,a in enumerate(slopes):
        dh=math.log1p((de[i]+dp[i])/(e[i]+p[i]))/(a+1)
        if not math.isfinite(dh) or dh<=0:
            raise ValueError("UNMODIFIED_FIRST_LAW_ENTHALPY_INCREMENT_INVALID")
        h[i+1]=h[i]+dh
    n=(e+p)*np.exp(-h)*C*C/(G*MB)/1e6
    if not (np.isfinite(h).all() and np.isfinite(n).all()
            and np.all(np.diff(h)>0) and np.all(n>0)):
        raise ValueError("UNMODIFIED_FIRST_LAW_RECONSTRUCTION_INVALID")
    return {"secant_cs2":source_cs2,"h":h,"n":n}

def source_comparison(p,e,candidate,ref_central_energy_geo,source_cs2=None):
    orig=source_thermo(p,e,candidate.alpha)
    p=np.asarray(p,float);e=np.asarray(e,float)
    el=np.asarray(candidate.e,float)
    if not (el.shape==e.shape and np.all(el>=e) and np.all(np.diff(el)>0)):
        raise ValueError("CANDIDATE_ENERGY_ENVELOPE_MISMATCH")
    lifted_cs2=np.diff(p)/np.diff(el)
    if np.max(lifted_cs2)>candidate.cap*(1+1e-9):
        raise ValueError("F42_CANDIDATE_CAUSAL_SECCANT_FAIL")
    frac=el/e-1.0
    affected=np.flatnonzero(frac>1e-14)
    if affected.size==0:
        first_changed=None
    else:
        k=int(affected[0])
        first_changed={"source_index":k,"pressure_geom_m_minus_2":float(p[k]),
                       "source_rho_g_cm3":float(e[k]*C*C/G*1e-3),
                       "lifted_rho_g_cm3":float(el[k]*C*C/G*1e-3)}
    cp=float(ref_central_energy_geo)
    if not (el[0] <=cp<=el[-1]):
        raise ValueError("F53_CENTRAL_ENERGY_OUTSIDE_F42_WFF1_ORIGINAL_SOURCE_SUPPORT")
    idx=int(np.clip(np.searchsorted(el,cp,side="right")-1,0,len(el)-2))
    pcenter=float(p[idx]+(cp-el[idx])/(el[idx+1]-el[idx])*(p[idx+1]-p[idx]))
    native_energy_at_same_pressure=float(e[idx]+(pcenter-p[idx])/(p[idx+1]-p[idx])*(e[idx+1]-e[idx]))
    candidate_h_at_pressure=float(candidate.values(np.array([pcenter]))[1][0])
    frac_center=float(cp/native_energy_at_same_pressure-1)
    # Compare first-law reconstructed h,n only at native pressure knots.
    n_candidate=(el+p)*np.exp(-candidate.hknots)*C*C/(G*MB)/1e6
    raw_sec=orig["secant_cs2"]
    result={
      "source_original_n_pressure_knots":len(p),
      "source_causal_secant_segments_total":len(raw_sec),
      "source_original_superluminal_secant_segments":int(np.count_nonzero(raw_sec>1+1e-11)),
      "source_original_max_secant_cs2_over_c2":float(np.max(raw_sec)),
      "source_original_min_secant_cs2_over_c2":float(np.min(raw_sec)),
      "source_original_first_superluminal_segment":next((int(i) for i in np.flatnonzero(raw_sec>1+1e-11)),None),
      "candidate_max_secant_cs2_over_c2":float(np.max(lifted_cs2)),
      "candidate_min_secant_cs2_over_c2":float(np.min(lifted_cs2)),
      "source_energy_changed_knots":int(affected.size),
      "source_energy_max_fractional_lift":float(np.max(frac)),
      "source_energy_median_fractional_lift":float(np.median(frac)),
      "source_energy_first_changed_node":first_changed,
      "source_raw_firstlaw_model_assumption":"same analytic piecewise e(p), explicit low-P alpha=0.6 cold-gas continuation and mu0=m_u; NOT native source baryon chemical potential",
      "source_vs_candidate_max_abs_enthalpy_knot_difference":float(np.max(np.abs(candidate.hknots-orig["h"]))),
      "source_vs_candidate_max_abs_n_knot_fraction_difference":float(np.max(np.abs(n_candidate/orig["n"]-1))),
      "F53_201x401_star_center_reference_rho_g_cm3":float(cp*C*C/G*1e-3),
      "F53_candidate_center_pressure_geom_m_minus_2":pcenter,
      "F53_candidate_center_pressure_index":idx,
      "F53_center_original_native_rho_at_same_pressure_g_cm3":float(native_energy_at_same_pressure*C*C/G*1e-3),
      "F53_center_original_vs_candidate_density_shift_at_equal_pressure_fraction":frac_center,
      "F53_candidate_center_integrated_enthalpy_model":candidate_h_at_pressure,
      "F53_comparison_star_not_rerun":True,
      "source_original_star_at_this_pressure":"NOT_SOLVED—PRESSURE_ALIGNED_EOS_ONLY",
      "global_physical_WFF1_EOS_causality_proven":False,
      "global_dynamical_stability":"NOT_TESTED",
      "XPSI_15D_source_native_Bayes":"NOT_RUN",
    }
    if source_cs2 is not None:
        cs=np.asarray(source_cs2,float)
        if cs.ndim==1 and cs.shape==p.shape:
            finite=np.isfinite(cs)
            result["JESTER_native_cs2_field_statistics"]={
                "size":len(cs),"finite_count":int(np.count_nonzero(finite)),
                "max_finite_reported":float(np.max(cs[finite])) if np.any(finite) else None,
                "count_reported_gt_1_if_dimensionless":int(np.count_nonzero(cs[finite]>1)),
                "semantics":"Raw NPZ cs2 field; do not substitute for exact C-RNS interpolated derivative"}
        else:
            result["JESTER_native_cs2_field_statistics"]={
                "source_field_shape":list(cs.shape),"error":"FIELD_NOT_SAME_SHAPE_AS_PRESSURE"}
    rows=[]
    for i in range(len(p)):
        rows.append({"source_index":i,"pressure_geom_m_minus_2":float(p[i]),
         "source_e_geom_m_minus_2":float(e[i]),"candidate_e_geom_m_minus_2":float(el[i]),
         "fractional_energy_lift":float(frac[i]),
         "source_h_with_explicit_coldgas_assumption":float(orig["h"][i]),
         "candidate_firstlaw_h":float(candidate.hknots[i]),
         "source_candidate_secant_cs2_raw":float(raw_sec[i]) if i<len(raw_sec) else None,
         "source_candidate_secant_cs2_lifted":float(lifted_cs2[i]) if i<len(raw_sec) else None})
    return result,rows

def reproduce_locked_source(npz_path,f44_path,f53_path):
    if sha(npz_path)!=NPZ_SHA or sha(f44_path)!=F44_SHA or sha(f53_path)!=F53_SHA:
        raise ValueError("F56_EXACT_SOURCE_SHA256_MISMATCH")
    with np.load(npz_path,allow_pickle=False) as npz:
        p=np.asarray(npz["p"],float);e=np.asarray(npz["e"],float)
        cs=np.asarray(npz["cs2"],float) if "cs2" in npz.files else None
    cand=Candidate(p,e,cap=.99,alpha=.6)
    rows,_=cand.rns_table(points=200,surface_depth=12)
    with zipfile.ZipFile(f44_path) as z:
        if z.testzip() is not None:raise ValueError("F44_ZIP_CRC_FAIL")
        recorded=json.loads(z.read("F44_direct_RNS_seven_candidates.json"))["eos"]["WFF1"]
        tabname=recorded["model_label"]+".rns"
        blob=z.read("eos_tables/"+tabname)
        if hashlib.sha256(blob).hexdigest()!=recorded["model_table_sha256"]:
            raise ValueError("F44_TABLE_CONTENT_SHA256_MISMATCH")
        original=np.loadtxt(io.BytesIO(blob),skiprows=1)
        if original.shape!=rows.shape:
            raise ValueError("SOURCE_TABLE_SHAPE_DRIFT")
        maxrel=float(np.max(np.abs(rows/original-1)))
        if maxrel>TABLE_REL_TOL:raise ValueError("F56_REBUILT_200_TABLE_DIFFERENT_FROM_ORIGINAL_C_INPUT")
    with zipfile.ZipFile(f53_path) as z:
        if z.testzip() is not None:raise ValueError("F53_ZIP_CRC_FAIL")
        source=json.loads(z.read("F53_WFF1_direct_C_constant_J_stars.json"))
        if (source["status"]!="PASS_SAMPLED_CONSTANT_J_TURNING_DIAGNOSTIC_NOT_GLOBAL_STABILITY"
            or source["WFF1_EOS_table_sha256"]!=recorded["model_table_sha256"]):
            raise ValueError("F53_WRONG_SOURCE_EOS_OR_UNVERIFIED_STATUS")
        ref=source["regenerated_F52_reference"]
        if abs(ref["ec_g_cm3"]-TARGET_EC_CGS)>1e6:
            raise ValueError("F53_REFERENCE_CENTRAL_DENSITY_DRIFT")
    return p,e,cs,cand,ref,maxrel,recorded["model_table_sha256"]

def run(npz,f44,f53,out,table_out):
    p,e,cs,cand,ref,maxrel,table_sha=reproduce_locked_source(npz,f44,f53)
    compare,rows=source_comparison(p,e,cand,ref["ec_g_cm3"]*1e3*G/(C*C),cs)
    report={
      "schema":"J0740_F56_WFF1_ORIGINAL_VS_F42_CAUSAL_LIFT_PHYSICAL_INPUT_AUDIT_V1",
      "status":"PASS_AUTHENTIC_SOURCE_VS_CANDIDATE_INPUT_DIAGNOSTIC_NOT_ASTROPHYSICAL_PROOF",
      "source_JESTER_commit":JESTER_COMMIT,
      "source_WFF1_NPZ_sha256":sha(npz),
      "source_F44_RNS_200tab_zip_sha256":sha(f44),
      "source_F53_real_C_constant_J_zip_sha256":sha(f53),
      "reference_200row_RNS_table_sha256":table_sha,
      "regenerated_200row_max_relative_difference":maxrel,
      "source_original_EOS_core_untouched":True,
      "candidate_is_modified_F42_EOS":True,
      "candidate_low_pressure_gas_assumption":"alpha=0.6, mu0=m_u",
      "source_native_tabulated_firstlaw_n_physical_proven":False,
      "comparison":compare
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+"\n")
    with table_out.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    return report

def main():
    a=argparse.ArgumentParser()
    for k in ("npz","f44","f53","out","table_out"):
        a.add_argument("--"+k.replace("_","-"),type=Path,required=True)
    v=a.parse_args()
    z=run(v.npz,v.f44,v.f53,v.out,v.table_out)
    print(json.dumps({"status":z["status"],"source":z["source_WFF1_NPZ_sha256"],
                      "comparison":z["comparison"]},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
