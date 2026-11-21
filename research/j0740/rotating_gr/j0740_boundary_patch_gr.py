"""Check seven rotating and static J0740 C/GR models after first-bin H(P) patch.

Same pinned seven JESTER NPZ files, same 196-point thermodynamic tables,
same stellar center densities, same RNS source commit apart from two documented
low-density interpolation functions. Does NOT touch 12.9 GB Salmi archive.
This is a sensitivity experiment. No EOS Bayes model posterior.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from j0740_absolute_enthalpy_gr import compare_at_same_center
from rns_boundary_patch import bounded_h_from_p,bounded_p_from_h

EOS=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
JESTER_SHA="e6768650ce992abfd1153a6833857572fe5cd230"
RNS_SHA="97e85d325a33e37f702306414533f6cd77812477"
ORIGINAL_JSON_SHA="d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"


def audit(prior:dict,patched_binary:Path,source_dir:Path,outdir:Path,patch_manifest:Path)->dict:
    if (prior.get("status")!="ALL_SEVEN_VALIDATED" or prior.get("validated_eos_count")!=7
            or prior.get("jester_upstream_commit")!=JESTER_SHA or prior.get("rns_upstream_commit")!=RNS_SHA
            or set(prior.get("eos",{}))!=set(EOS)):
        raise ValueError("Original seven EOS GR source identity mismatch")
    from jester_to_rns import from_jester_npz,write_rns
    from rns_benchmark import run_rns, OBSERVED_SPIN_HZ, RNS_COMMIT
    from axis_ratio_rns import run_rns_at_spin_with_ratio_fallback
    from seven_eos_sequence import stable_source_radius_at_mass
    if RNS_COMMIT!=RNS_SHA:raise ValueError("Pinned RNS upstream commit changed")
    patch=json.loads(patch_manifest.read_text())
    if patch.get("schema")!="j0740-RNS-C-first-logh-bin-guard-v1":
        raise ValueError("Unexpected patched C source manifest")
    results={}
    for name in EOS:
        old=prior["eos"][name]
        try:
            src=source_dir/(name+".npz")
            digest=hashlib.sha256(src.read_bytes()).hexdigest()
            if digest!=old["source_npz_sha256"]:raise ValueError("Original JESTER EOS NPZ SHA mismatch")
            rows,meta=from_jester_npz(src,points=196)
            path=outdir/(name+"_same_legacy_H_196pt.rns")
            write_rns(path,rows)
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            # The original H(P_min)=1 is retained; only C first-bin inverse is bounded.
            err=[]
            for pp in np.geomspace(rows[0,1],rows[1,1],16):
                hh=bounded_h_from_p(rows,float(pp))
                inverse=bounded_p_from_h(rows,hh)
                err.append(abs(inverse/pp-1))
            rho_rot=float(old["rns_rotating_at_target"]["central_energy_density_g_cm3"])
            rho_sta=float(old["rns_static_at_same_gravitational_mass"]["central_energy_density_g_cm3"])
            rot=run_rns_at_spin_with_ratio_fallback(patched_binary,path,
                  central_density=rho_rot,spin_hz=OBSERVED_SPIN_HZ)
            sta=run_rns(patched_binary,path,central_density=rho_sta,spin_hz=0)
            delta_rot=compare_at_same_center(old["rns_rotating_at_target"],rot)
            delta_sta=compare_at_same_center(old["rns_static_at_same_gravitational_mass"],sta)
            source_static_ref,stable_branch=stable_source_radius_at_mass(src,sta["mass_msun"])
            static_tov_delta=float(sta["radius_eq_km"]-source_static_ref)
            results[name]={
                "status":"PATCHED_RNS_GR_ROTATING_STATIC_COMPUTED",
                "original_npz_sha256":digest,
                "rns_196_input_regenerated_text_sha256":sha,
                "rns_prior_historical_input_text_sha256":old["rns_table_sha256"],
                "rns_text_byte_identity_match":sha==old["rns_table_sha256"],
                "first_pressure_bin_inverse_max_relative_error":float(max(err)),
                "first_H_cgs":float(rows[0,2]),
                "next_H_cgs":float(rows[1,2]),
                "rotating":rot,"static":sta,
                "rotating_delta":delta_rot,"static_delta":delta_sta,
                "jester_TOV_static_reference_radius_km_at_corrected_mass":source_static_ref,
                "rns_patched_static_minus_JESTER_TOV_km":static_tov_delta,
                "source_TOV_branch":stable_branch,
                "static_source_TOV_tolerance_0p25km_pass":bool(abs(static_tov_delta)<=0.25),
            }
        except Exception as exc:
            results[name]={"status":"PATCHED_RNS_MODEL_FAILED","error_type":type(exc).__name__,"reason":str(exc)[:1600]}
        print(name,results[name]["status"],flush=True)
    good=sum(x["status"]=="PATCHED_RNS_GR_ROTATING_STATIC_COMPUTED" for x in results.values())
    return {"schema":"j0740-seven-eos-surface-first-bin-interpolation-C-GR-v1",
            "status":"ALL_SEVEN_PATCHED_RNS_GR_COMPUTED" if good==7 else "PARTIAL_PATCHED_GR_NOT_FINAL",
            "computed_eos":good,"original_GR_run":42353019033,"original_GR_json_sha256":ORIGINAL_JSON_SHA,
            "original_RNS_C_commit":RNS_SHA,"pinned_JESTER_commit":JESTER_SHA,
            "patched_C_equil_sha256":patch.get("source_post_patch_sha256"),
            "source_C_equil_sha256":patch.get("source_pre_patch_sha256"),
            "science_caveats":["At unchanged central energy density, not fixed M_G",
              "Patched C first EOS bin only, not a physical low-pressure crust extension",
              "Static comparison with JESTER TOV evaluated per corrected static mass",
              "Original native crust negative cs² and supra-luminal EOS centers not resolved",
              "No X-PSI native NICER/XMM 15D likelihood or EOS evidence"],
            "eos":results}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--prior",type=Path,required=True)
    p.add_argument("--patched-rns",type=Path,required=True)
    p.add_argument("--jester-dir",type=Path,required=True)
    p.add_argument("--patch-manifest",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    raw=a.prior.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ORIGINAL_JSON_SHA:
        raise ValueError("Original successful RNS 7EOS JSON checksum mismatch")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    data=audit(json.loads(raw),a.patched_rns,a.jester_dir,a.out.parent,a.patch_manifest)
    a.out.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    if data["computed_eos"]!=7:
        raise SystemExit("Some patched C/GR models failed; full evidence preserved")

if __name__=='__main__':main()
