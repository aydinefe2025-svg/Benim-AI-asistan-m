"""F56: original JESTER WFF1 vs F42 causal-lift physical identity audit.

This experiment uses the SHA-pinned *unmodified* WFF1 source NPZ,
its own native cs2 array and JESTER source TOV M-R curve, and regenerates
the F42 mathematical-candidate EOS at exactly the original pressure nodes.
It does NOT infer a source-native rotating C-RNS model or final EOS Bayes.
The source JESTER M-R data are previously-computed models, not new TOV runs.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"f42"))
sys.path.insert(0,str(HERE.parent/"rotating_gr"))
from f42_causal_firstlaw_candidates import Candidate, C, G, MB
from source_native_global_gate import audit_arrays

SOURCE_WFF1_SHA="119b8a25435faeddf00f5d3638f3ff2ff00283ce60caacc24cc37c6e2e030ed3"
F42_ARCHIVE_SHA="c8d8cdc9804a702860ab1af65b60fa25dfac0f74fce9ec6347c4271ea3353115"
SOURCE_JESTER_COMMIT="e6768650ce992abfd1153a6833857572fe5cd230"
MASS_TARGET=2.073
F53_CANDIDATE_CENTER_CGS=2.900e15
F53_200ROW_DIRECT_C_FIXED_J_MASS=2.1198764740646654
EXPECTED_F43_CANDIDATE_TABLE_SHA="0ac47df0d250baef55c2b046a809ed433215a31332b268177babf667e306f02f"


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def rising_branch_radius(masses, radii, target=MASS_TARGET):
    """Only interpolate inside an actually sampled ascending native M-R segment."""
    m=np.asarray(masses,float)
    r=np.asarray(radii,float)
    if not (m.ndim==1 and r.shape==m.shape and m.size>=30
            and np.isfinite(m).all() and np.isfinite(r).all()
            and np.all(m>0) and np.all(r>5) and np.all(r<40)
            and math.isfinite(target) and target>0):
        raise ValueError("BAD_SOURCE_JESTER_NATIVE_MR_SHAPE_OR_UNITS")
    peak=int(np.argmax(m))
    cross=np.where((m[:-1]<target)&(m[1:]>=target)&(np.arange(len(m)-1)<peak))[0]
    if len(cross)!=1:
        raise ValueError("NO_UNIQUE_JESTER_RISING_BRANCH_SOURCE_MR_CROSSING")
    i=int(cross[0])
    if not (np.all(np.diff(m[max(0,i-5):min(len(m),i+7)])>0)
            and m[i]<target<m[i+1]):
        raise ValueError("NONMONOTONIC_NATIVE_SOURCE_MR_NEAR_TARGET")
    radius=float(r[i]+(r[i+1]-r[i])*(target-m[i])/(m[i+1]-m[i]))
    return {"target_Msun":target, "rising_branch_interpolated_radius_km":radius,
            "source_native_TOV_MR_not_new_GR_solution":True,
            "source_native_TOV_MR_neighbor_stars":[
                {"mass_msun":float(m[j]),"radius_km":float(r[j])} for j in (i,i+1)],
            "rising_target_mass_bracket_index":i,
            "source_TOV_mass_sample_max_msun":float(m[peak]),
            "source_TOV_max_is_LAST_SAMPLED_NOT_PROVEN_GLOBAL":bool(peak==len(m)-1),
            "number_native_JESTER_TOV_nodes":len(m),
            "only_local_MR_interpolation_not_new_star":True}


def build(npz,f43):
    if sha(npz)!=SOURCE_WFF1_SHA:
        raise ValueError("F56_ORIGINAL_JESTER_WFF1_SOURCE_SHA_MISMATCH")
    F43=json.loads(Path(f43).read_text())
    if F43.get("source_F42_artifact_sha256")!=F42_ARCHIVE_SHA:
        raise ValueError("F43_LOCKED_F42_ARTIFACT_MISMATCH")
    f43w=F43["eos"]["WFF1"]
    if f43w.get("source_rns_sha256")!=EXPECTED_F43_CANDIDATE_TABLE_SHA:
        raise ValueError("F43_SOURCE_MATHEMATICAL_CANDIDATE_CHANGED")
    root=f43w["first_stable_2p073_root"]["fine"]
    if abs(root["mass_msun"]-MASS_TARGET)>.001:
        raise ValueError("F43_STATIC_TARGET_MASS_DRIFT")
    with np.load(npz,allow_pickle=False) as z:
        source={k:np.asarray(z[k],float) for k in
                ("p","e","n","h","cs2","masses_EOS","radii_EOS")}
    p,e,n,h,cs2=[source[k] for k in ("p","e","n","h","cs2")]
    if not (p.ndim==e.ndim==n.ndim==h.ndim==cs2.ndim==1
            and len(p)==len(e)==len(n)==len(h)==len(cs2)
            and np.all(p>0) and np.all(e>0) and np.all(np.diff(p)>0)):
        raise ValueError("NATIVE_WFF1_INVALID_SOURCE_THERMO_ARRAY")
    original_mr=rising_branch_radius(source["masses_EOS"],source["radii_EOS"])
    candidate=Candidate(p,e,cap=.99,alpha=.6)
    lift=np.divide(candidate.e-e,e)
    speed_native_positive=np.asarray(cs2,float)
    first_super=np.flatnonzero(cs2>1+1e-8)
    first_nonpos=np.flatnonzero(cs2<=0)
    center_geom=F53_CANDIDATE_CENTER_CGS*1e3*G/C**2
    source_global=audit_arrays(p,e,n,h,cs2,center_e=center_geom)
    if first_super.size==0:
        raise ValueError("EXPECTED_ORIGINAL_WFF1_SUPERLUMINAL_SOURCE_SCREEN_DRIFT")
    if first_nonpos.size==0:
        raise ValueError("EXPECTED_ORIGINAL_WFF1_NONPOSITIVE_SOURCE_KNOT_DRIFT")
    if source_global["sampled_source_screen"]!="FAIL_IN_STAR":
        raise ValueError("EXPECTED_SOURCE_CAUSAL_INSTAR_FAILURE_MISSING")
    source_energy_cgs=e*C*C/G*1e-3
    ix=int(np.argmax(lift))
    i_s=int(first_super[0])
    ecenter=center_geom
    if not candidate.e[0]<ecenter<candidate.e[-1]:
        raise ValueError("F53_CANDIDATE_CENTER_OUTSIDE_EOS_SUPPORT")
    pressure_center=float(np.interp(ecenter,candidate.e,p))
    original_ec_at_candidate_center_p=float(np.interp(pressure_center,p,e))
    candidate_ec_at_candidate_center_p=float(np.interp(pressure_center,p,candidate.e))
    firstlaw_candidate_e,h_c,n_c,cs2_c=candidate.values(np.array([pressure_center]))
    if abs(float(firstlaw_candidate_e[0])/ecenter-1)>1e-7:
        raise ValueError("F56_CANDIDATE_CENTER_EPSILON_INVERSE_MISMATCH")
    native_r=original_mr["rising_branch_interpolated_radius_km"]
    f43_r=float(root["radius_km"])
    result={
        "schema":"J0740_F56_NATIVE_WFF1_VS_F42_NEW_CANDIDATE_SOURCE_PHYSICS_V1",
        "status":"SOURCE_NATIVE_FAILS_GLOBAL_AND_IN_STAR_CAUSAL_SCREEN__CANDIDATE_IS_DIFFERENT_EOS",
        "source_native_npz_sha256":sha(npz),
        "source_commit":SOURCE_JESTER_COMMIT,
        "F43_archive_comparison_sha256":sha(f43),
        "F43_F42_original_artifact_sha256":F42_ARCHIVE_SHA,
        "source_unchanged":True,
        "native_source_nodes":len(p),
        "native_source_energy_nonincreasing_edges":int(np.count_nonzero(np.diff(e)<=0)),
        "native_cs2_source_max":float(np.max(cs2)),
        "native_cs2_nonpositive_node_count":int(len(first_nonpos)),
        "native_cs2_superluminal_node_count":int(len(first_super)),
        "native_cs2_first_superluminal_node_index":i_s,
        "native_cs2_first_superluminal_energy_equiv_g_cm3":float(source_energy_cgs[i_s]),
        "native_negative_cs2_first_node_index":int(first_nonpos[0]),
        "native_original_in_star_center_screen":source_global,
        "F42_candidate_alpha":candidate.alpha,
        "F42_candidate_cap_cs2":candidate.cap,
        "F42_candidate_max_caused_energy_fractional_lift":float(np.max(lift)),
        "F42_candidate_source_changed_node_count":int(np.count_nonzero(lift>1e-15)),
        "F42_candidate_max_lift_source_index":ix,
        "F42_candidate_max_lift_pressure_geometry":float(p[ix]),
        "F42_candidate_max_lift_orig_energy_geometry":float(e[ix]),
        "F42_candidate_max_lift_new_energy_geometry":float(candidate.e[ix]),
        "F42_candidate_max_secant_cs2":float(np.max(candidate.cs2)),
        "F53_candidate_center_at_2p9e15_cgs":{
            "equivalent_energy_density_geom":float(ecenter),
            "candidate_pressure_at_center_geom":pressure_center,
            "native_epsilon_at_same_pressure_geom":original_ec_at_candidate_center_p,
            "candidate_epsilon_at_same_pressure_geom":candidate_ec_at_candidate_center_p,
            "relative_energy_change_at_same_pressure":candidate_ec_at_candidate_center_p/original_ec_at_candidate_center_p-1,
            "same_pressure_does_not_equal_same_star":True,
            "F53_real_C_fixed_J_reference_mass_msun":F53_200ROW_DIRECT_C_FIXED_J_MASS,
            "no_source_native_C_star_at_same_target_was_computed":True},
        "native_source_JESTER_existing_static_MR":original_mr,
        "F43_F42_candidate_static_real_TOV_at_2p073":{
            "mass_msun":float(root["mass_msun"]),
            "radius_km":f43_r,
            "source_candidate_RNS_table_sha256":EXPECTED_F43_CANDIDATE_TABLE_SHA,
            "source_F42_physically_modified":True},
        "new_candidate_minus_native_existing_static_radius_at_2p073_km":f43_r-native_r,
        "source_radii_method_caveat":"Two different previously solved static M-R products; JESTER native existing curve locally interpolated to M2.073, F43 candidate independently integrated TOV. Not a same-EOS numerical convergence experiment.",
        "source_original_unmodified_causality_acceptance":"FAIL_SAMPLED_SOURCE",
        "new_candidate_physical_nuclear_EOS_identity":"NOT_ORIGINAL_WFF1",
        "baryonic_rest_mass_and_crust_validation":"NOT_ESTABLISHED",
        "native_source_rotating_gr_star":"NOT_RUN",
        "native_photon_XPSI_7_EOS_Bayes":"NOT_RUN",
        "turning_point_global_dynamical_stability":"NOT_ESTABLISHED",
        "source_mr_sample_is_not_a_global_stability_proof":True,
    }
    if result["native_cs2_source_max"]<=1:
        raise ValueError("WFF1_EXPECTED_NATIVE_ACAUSALITY_CONTRADICTED")
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--npz",type=Path,required=True)
    p.add_argument("--f43",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    result=build(a.npz,a.f43)
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:result[k] for k in (
        "status","native_cs2_source_max","native_cs2_superluminal_node_count",
        "F42_candidate_max_caused_energy_fractional_lift",
        "new_candidate_minus_native_existing_static_radius_at_2p073_km")},
        sort_keys=True),flush=True)

if __name__=="__main__":main()
