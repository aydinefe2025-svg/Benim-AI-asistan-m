"""Independent 196→200 EOS table-resolution stress test of prior 7/7 RNS models.

At identical model central density and spin, regenerate a source-matched EOS
table with 200 thermodynamic points rather than 196 and solve actual RNS GR
again. This is a finite resolution sensitivity check, NOT an exact convergence
extrapolation, EOS posterior, or constant-gravitational-mass comparison.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from jester_to_rns import from_jester_npz,write_rns
from rns_benchmark import RNS_COMMIT,run_rns
from axis_ratio_rns import run_rns_at_spin_with_ratio_fallback

EOS=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
JESTER_COMMIT="e6768650ce992abfd1153a6833857572fe5cd230"
RNS_JSON_SHA256="d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"
MASS_DELTA_SCREEN=0.020
RADIUS_DELTA_SCREEN_KM=0.15


def compare_model(original,repeat):
    if not all(k in original and k in repeat for k in ("mass_msun","radius_eq_km","central_energy_density_g_cm3","spin_hz_reported")):
        raise ValueError("Incomplete RNS model")
    m0,m1=float(original["mass_msun"]),float(repeat["mass_msun"])
    r0,r1=float(original["radius_eq_km"]),float(repeat["radius_eq_km"])
    rho0,rho1=float(original["central_energy_density_g_cm3"]),float(repeat["central_energy_density_g_cm3"])
    if not all(math.isfinite(x) for x in (m0,m1,r0,r1,rho0,rho1)):
        raise ValueError("Invalid nonfinite RNS output")
    if not math.isclose(rho0,rho1,rel_tol=5e-6,abs_tol=1e9):
        raise ValueError("200pt and 196pt model central densities disagree")
    if not (0<m0<4 and 0<m1<4 and 6<r0<30 and 6<r1<30):
        raise ValueError("Unphysical RNS mass/radius")
    dm=m1-m0
    dr=r1-r0
    return {
      "original_196_M_msun":m0,
      "rerun_200_M_msun":m1,
      "delta_mass_msun":dm,
      "original_196_radius_eq_km":r0,
      "rerun_200_radius_eq_km":r1,
      "delta_radius_eq_km":dr,
      "same_central_density_g_cm3":rho0,
      "spin_hz_original":float(original["spin_hz_reported"]),
      "spin_hz_200":float(repeat["spin_hz_reported"]),
      "mass_abs_tol_msun":MASS_DELTA_SCREEN,
      "radius_abs_tol_km":RADIUS_DELTA_SCREEN_KM,
      "screen_pass":bool(abs(dm)<=MASS_DELTA_SCREEN and abs(dr)<=RADIUS_DELTA_SCREEN_KM),
      "warning":"Same central density and nominal spin comparison; not same gravitational/baryonic mass. One two-point refinement is NOT systematic grid convergence."
    }


def audit(rns,binary,source_dir,outdir):
    if not (rns.get("status")=="ALL_SEVEN_VALIDATED" and rns.get("validated_eos_count")==7
            and rns.get("jester_upstream_commit")==JESTER_COMMIT
            and rns.get("rns_upstream_commit")==RNS_COMMIT
            and set(rns.get("eos",{}))==set(EOS)):
        raise ValueError("Prior successful 196pt RNS source identity mismatch")
    out={}
    for name in EOS:
        record=rns["eos"][name]
        try:
            src=source_dir/(name+".npz")
            digest=hashlib.sha256(src.read_bytes()).hexdigest()
            if digest!=record["source_npz_sha256"]:
                raise ValueError("source NPZ SHA256 mismatch")
            rows,meta=from_jester_npz(src,points=200)
            path=outdir/(f"eos_{name}_200")
            write_rns(path,rows)
            rot0=record["rns_rotating_at_target"]
            sta0=record["rns_static_at_same_gravitational_mass"]
            rot200=run_rns_at_spin_with_ratio_fallback(
                binary,path,central_density=float(rot0["central_energy_density_g_cm3"]),
                spin_hz=float(rns["spin_hz"]))
            sta200=run_rns(
                binary,path,central_density=float(sta0["central_energy_density_g_cm3"]),
                spin_hz=0.0)
            rotating=compare_model(rot0,rot200)
            static=compare_model(sta0,sta200)
            ok=rotating["screen_pass"] and static["screen_pass"]
            out[name]={
              "status":"196_200_EOS_TABLE_STRESS_SCREEN_PASS" if ok else "MATERIAL_196_200_EOS_TABLE_RESOLUTION_SENSITIVITY",
              "source_npz_sha256":digest,
              "rns_196_table_sha256":record["rns_table_sha256"],
              "rns_200_table_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
              "source_thermodynamic_nodes":meta["source_points"],
              "original_eos_nodes":196,
              "refined_eos_nodes":200,
              "rotating_same_center_density":rotating,
              "static_same_center_density":static,
              "rotating_solver_mode":rot200.get("solver_mode","RNS_C_SETSPIN"),
            }
        except Exception as exc:
            out[name]={"status":"RNS_200_EOS_MODEL_NUMERICAL_FAILURE",
                       "error_type":type(exc).__name__,"reason":str(exc)[:1000]}
        print(name,out[name]["status"],flush=True)
    good=sum(x["status"]=="196_200_EOS_TABLE_STRESS_SCREEN_PASS" for x in out.values())
    return {
      "schema":"j0740-7eos-rns-196-vs-200-gr-model-sensitivity-v1",
      "status":"ALL_SEVEN_196_TO_200_STRESS_SCREEN_PASS" if good==7 else "PARTIAL_196_TO_200_STRESS_NOT_VALIDATED",
      "matched_models":good,"total_models":7,
      "rns_upstream_commit":RNS_COMMIT,"jester_upstream_commit":JESTER_COMMIT,
      "rns_original_run":42353019033,
      "rns_original_json_sha256":RNS_JSON_SHA256,
      "comparison":"actual RNS 200 point EOS regenerated at exactly same central density and spin as prior 196 model",
      "limitations":["single-step 196 to 200 EOS resolution test is a sensitivity screen, NOT continuum extrapolation",
                     "fixed central density, NOT fixed gravitational or baryonic mass",
                     "RNS spacetime grid unchanged (MDIVxSDIV=151x301)",
                     "No X-PSI nuisance prior marginalization, photon likelihood, or EOS Bayes factors"],
      "eos":out
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rns-json",type=Path,required=True)
    p.add_argument("--rns",type=Path,required=True)
    p.add_argument("--jester-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    raw=a.rns_json.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=RNS_JSON_SHA256:
        raise ValueError("Prior RNS JSON digest changed")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    result=audit(json.loads(raw),a.rns,a.jester_dir,a.out.parent)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(result["status"],"PASS",result["matched_models"],"/7",flush=True)
    if result["matched_models"]!=7:
        raise SystemExit("RNS 196 vs 200 numerical sensitivity requires review; evidence preserved")


if __name__=="__main__":
    main()
