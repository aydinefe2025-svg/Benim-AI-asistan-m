#!/usr/bin/env python3
"""F75: source-prior-corrected posterior-flow line integrals on existing F51 GR roots.

Uses only the Amsterdam Salmi posterior (no Maryland duplicate), JESTER's
source-pinned 100k equal-weight sample, the archive-hash-pinned Salmi prior,
and previously computed F51 direct C/GR roots. This is a KDE posterior/prior
likelihood approximation over a common measured mass window, NOT EOS evidence.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"f51"))
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.interpolate import RegularGridInterpolator
from scipy.integrate import simpson
from scipy.optimize import brentq
from scipy.stats import truncnorm
import f51_extended_support_audit as f51

JESTER_COMMIT="e6768650ce992abfd1153a6833857572fe5cd230"
NPZ_FILE="jesterTOV/inference/data/NICER/J07406620_amsterdam_gamma_NICERXMM_equal_weights_recent.npz"
NPZ_BLOB_SHA="8a5adb339699ea1065aa858bdab406de11b22f72"
NICER_FILE="jesterTOV/inference/likelihoods/nicer.py"
NICER_BLOB_SHA="69bd82517ff3f5a8857cd514c711bc5bc039a771"
PRIOR_SHA256="ecabb879c38d4e4e343e5e304e1be39d87a7b0a35d7077454e4677ea1458aa93"
MASS_MU=2.082
MASS_SIG=0.0703
FREQ_HZ=346.53637
RG_KM=1.47662512
C_M_S=299792458.
R_LO=3.*RG_KM
R_HI=16.
Z_STAR=0.5780634963185343

def git_blob_sha(path:Path)->str:
    raw=path.read_bytes()
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\x00"+raw).hexdigest()

def mass_pdf(m):
    a=np.asarray(m,dtype=float)
    return truncnorm.pdf(a,-5.,5.,loc=MASS_MU,scale=MASS_SIG)

def critical_radius(m:float)->float:
    if not MASS_MU-5*MASS_SIG<=m<=MASS_MU+5*MASS_SIG:
        raise ValueError("F75_MASS_OUTSIDE_SOURCE_SUPPORT")
    def f(r):
        z=RG_KM*m/r
        eps=(2*math.pi*FREQ_HZ)**2*(r*1000.)**3/(RG_KM*1000.*m*C_M_S**2)
        return r*(1.+eps*(-.788+1.030*z))-3.01*RG_KM*m
    return brentq(f,R_LO,R_HI,xtol=1e-12)

def source_pi_eff(m,r):
    m=np.asarray(m,dtype=float);r=np.asarray(r,dtype=float)
    out=np.zeros(np.broadcast_shapes(m.shape,r.shape),dtype=float)
    mm,rr=np.broadcast_arrays(m,r)
    valid=(mm>=MASS_MU-5*MASS_SIG)&(mm<=MASS_MU+5*MASS_SIG)&(rr<=R_HI)
    if np.any(valid):
        rcrit=np.array([critical_radius(float(x)) for x in mm[valid]])
        valid2=valid.copy()
        valid2[valid]=rr[valid]>=rcrit
        out[valid2]=mass_pdf(mm[valid2])/((R_HI-R_LO)*Z_STAR)
    return out

def build_kde(mass,radius,bw_m,bw_r,n=500):
    mass=np.asarray(mass,dtype=float);radius=np.asarray(radius,dtype=float)
    if mass.shape!=(100000,) or radius.shape!=mass.shape or not np.isfinite(mass).all() or not np.isfinite(radius).all():
        raise ValueError("F75_BAD_POSTERIOR_SAMPLE_SHAPE")
    me=np.linspace(float(mass.min()-.08),float(mass.max()+.08),n+1)
    re=np.linspace(max(0.,float(radius.min()-.8)),float(radius.max()+.8),n+1)
    mg=(me[:-1]+me[1:])/2;rg=(re[:-1]+re[1:])/2
    dm=float(me[1]-me[0]);dr=float(re[1]-re[0])
    counts=np.histogram2d(mass,radius,bins=(me,re))[0].astype(float)
    q=gaussian_filter(counts,sigma=(bw_m/dm,bw_r/dr),mode="constant")
    q/=float(np.sum(q)*dm*dr)
    # Apply source hard support before interpolation; leakage from smoothing
    # beyond the source prior is set to zero and the retained posterior is
    # renormalized. The constant normalization cancels from EOS ratios.
    for i,m in enumerate(mg):
        rc=critical_radius(float(m)) if MASS_MU-5*MASS_SIG<=m<=MASS_MU+5*MASS_SIG else math.inf
        q[i,(rg<rc)|(rg>R_HI)]=0.
    norm=float(np.sum(q)*dm*dr)
    if not norm>0:raise ValueError("F75_KDE_EMPTY_AFTER_NATIVE_SUPPORT")
    q/=norm
    integral=float(np.sum(q)*dm*dr)
    interp=RegularGridInterpolator((mg,rg),q,bounds_error=True)
    return mg,rg,q,interp,{"mass_bw_msun":bw_m,"radius_bw_km":bw_r,
        "grid_shape":[n,n],"integral_after_hard_support":integral,
        "preclip_leakage_fraction":1.-norm}

def analyze(npz_path:Path,nicer_source:Path,root_archives:dict[str,Path],f44:Path,f48:Path,f49:Path):
    if git_blob_sha(npz_path)!=NPZ_BLOB_SHA:raise ValueError("F75_JESTER_NPZ_BLOB_DRIFT")
    if git_blob_sha(nicer_source)!=NICER_BLOB_SHA:raise ValueError("F75_JESTER_LIKELIHOOD_BLOB_DRIFT")
    curves=f51.load_verified_curves(root_archives,f44,f48)
    with np.load(npz_path,allow_pickle=False) as z:
        mass=np.asarray(z["mass"],float);radius=np.asarray(z["radius"],float)
    configs=[(.012,.15),(.018,.25),(.025,.35)]
    output={"schema":"A01.01.51_F75_JESTER_q_over_Salmi_pi_eff_on_F51_roots_v1",
      "status":"SOURCE_PRIOR_CORRECTED_KDE_APPROXIMATION_COMMON_WINDOW_ONLY",
      "data_lineage":{"jester_commit":JESTER_COMMIT,"npz_git_blob_sha1":NPZ_BLOB_SHA,
        "nicer_py_git_blob_sha1":NICER_BLOB_SHA,"archived_native_prior_sha256":PRIOR_SHA256,
        "posterior_samples":len(mass),"posterior_group":"Amsterdam Salmi gamma NICER+XMM only",
        "maryland_likelihood_multiplied":False,"observed_spin_hz":FREQ_HZ},
      "prior":{"formula":"pi_eff(M,R)=truncnorm(M;2.082,0.0703,±5σ)*I[Rcrit(M)<=R<=16]/((16-3*RG_KM)*Z_STAR)",
        "Z_star":Z_STAR,"global_source_prior_probability_integral":1.0,
        "target_radio_mass_prior":"same truncated Gaussian once; cancels algebraically against source mass factor in pi_eff",
        "pi_target_over_pi_eff_constant_km":(R_HI-R_LO)*Z_STAR},
      "estimand":"I_i ∝ ((16-3*RG_KM)*Z_STAR) * integral[q_KDE(M,R_eq,i(M)) dM] over shared direct-root interval; q is a source posterior approximation",
      "model_scope":"The seven F51 direct RNS curves are F42 causal-lift candidate barotropes, not the seven original nuclear microphysical EOS; no EOS prior or posterior probabilities assigned.",
      "scores":{},"limitations":["KDE posterior density approximation; not original event-level X-PSI photon likelihood.",
        "Only common 1.89–2.10 Msun mass interval with existing direct roots; no extrapolation or tail completion.",
        "F51 candidate EOS inputs are not original nuclear EOS; no model probabilities or physical EOS acceptance claimed.",
        "No global fixed-J stability gate; no full target EOS prior."]}
    for bw_m,bw_r in configs:
        mg,rg,q,interp,diag=build_kde(mass,radius,bw_m,bw_r)
        per={}
        for name,curve in curves.items():
            mm=curve["common_m"];rr=curve["common_r"]
            pi=source_pi_eff(mm,rr)
            if np.any(pi<=0):
                raise ValueError("F75_DIRECT_ROOT_OUTSIDE_SOURCE_PRIOR_"+name)
            points=np.column_stack((mm,rr))
            qline=np.asarray(interp(points),dtype=float)
            ratio=mass_pdf(mm)/pi
            integrand=ratio*qline
            raw=float(simpson(integrand,x=mm))
            support_prob=f51.prior_probability(float(mm[0]),float(mm[-1]))
            per[name]={"source_prior_corrected_integral":raw,
              "relative_to_common_equal_support":raw,
              "conditional_common_window_integral":raw/support_prob,
              "mass_prior_coverage":support_prob,
              "log_integral":math.log(raw) if raw>0 else None,
              "q_line_integral_unweighted":float(simpson(qline,x=mm)),
              "min_source_pi_eff":float(np.min(pi)),"max_source_pi_eff":float(np.max(pi))}
        # Scores are reported as ratios only within this explicitly restricted
        # candidate set and window. Do not interpret them as model posterior.
        scale=max(v["source_prior_corrected_integral"] for v in per.values())
        for v in per.values():v["ratio_to_largest_restricted_score"]=v["source_prior_corrected_integral"]/scale
        output["scores"][f"mass_bw={bw_m}_radius_bw={bw_r}"]= {"kde_diagnostic":diag,
            "models":per,"rank_within_restricted_set_only":sorted(per,key=lambda k:-per[k]["source_prior_corrected_integral"])}
    return output

def main():
    p=argparse.ArgumentParser()
    for name in ("npz","nicer_source","f44","f48","f49","curves_dir","out"):
        p.add_argument("--"+name.replace("_","-"),type=Path,required=True)
    a=p.parse_args()
    archives={n:a.curves_dir/("F46_"+n+".zip") for n in f51.EOS}
    r=analyze(a.npz,a.nicer_source,archives,a.f44,a.f48,a.f49)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":r["status"],"scores":r["scores"]},indent=2))

if __name__=="__main__":main()
