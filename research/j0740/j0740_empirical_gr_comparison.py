"""F30 empirical 2020 rotation fit vs verified 7-EOS full-GR RNS models.

This is an *existing evidence* comparison at the same gravitational mass and
spin: original F30 source knots + original 2026-11-07 RNS evidence only.
No NICER event-level likelihood, posterior samples, or large archives used.

CAUTION: F30 approximation corrects a static sequence at same baryon mass,
whereas the RNS radius difference is at same gravitational mass. We compare
predicted rotating R_eq(M_G) values at identical M_G, NOT the two corrections
at identical baryonic mass. F30 static source knots also have interpolation
error relative to RNS C; that contribution is kept separate below.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np

from rotation_same_baryon_audit import eos_at_rotating_mass

EOS=("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")
KNOTS_SHA256="9afb936763700424cbf359e325ff09f241bc0029ae83d90cc686a0bc11ce19a8"
RNS_JSON_SHA256="b7c20146d0438433c43e3ebb84c93342a551abd33371d58aa606a8b935cd592b"
RNS_SOURCE_RUN=42375488704
EXPECTED_MASS=2.073
EXPECTED_SPIN=346.536369


def verify_bytes(path:Path, expected:str)->str:
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=expected:
        raise ValueError(f"Source evidence SHA256 mismatch for {path.name}: {actual}")
    return actual


def compare_curve(knot_pairs, gr_row, mass:float, spin:float)->dict:
    pairs=np.asarray(knot_pairs,dtype=float)
    if (pairs.ndim!=2 or pairs.shape[1]!=2 or len(pairs)<4 or
            not np.all(np.isfinite(pairs)) or np.any(pairs<=0) or
            np.any(np.diff(pairs[:,0])<=0)):
        raise ValueError("Invalid strictly increasing source static M-R knots")
    if not (float(pairs[0,0])<=mass<=float(pairs[-1,0])):
        raise ValueError("Target mass outside F30 source static EOS support")
    if gr_row.get("status")!="MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED":
        raise ValueError("Unvalidated source EOS in GR artifact")
    rot=gr_row["rns_rotating_at_target"]
    stat=gr_row["rns_static_at_same_gravitational_mass"]
    for star in (rot,stat):
        if abs(float(star["mass_msun"])-mass)>0.0016:
            raise ValueError("GR stellar model is not fixed to intended gravitational mass")
        if not (6<float(star["radius_eq_km"])<30):
            raise ValueError("GR star radius outside scientific range")
    if abs(float(rot["spin_hz_reported"])-spin)>0.251:
        raise ValueError("GR star rotational frequency inconsistent")
    if abs(float(stat["spin_hz_reported"]))>0.11:
        raise ValueError("GR static control is not nonrotating")
    fit=eos_at_rotating_mass(pairs[:,0],pairs[:,1],mass,frequency_hz=spin)
    old_rot=float(fit["R_equatorial_rotating_km"])
    gr_rot=float(rot["radius_eq_km"])
    old_static=float(np.interp(mass,pairs[:,0],pairs[:,1]))
    gr_static=float(stat["radius_eq_km"])
    old_corr=old_rot-old_static
    gr_corr=gr_rot-gr_static
    source_static_offset=old_static-gr_static
    total=old_rot-gr_rot
    if not math.isclose(total,old_corr-gr_corr+source_static_offset,rel_tol=0,abs_tol=2e-12):
        raise AssertionError("Physical radius difference decomposition failed")
    return {
        "mass_msun":mass,
        "observed_spin_hz":spin,
        "f30_empirical_fit_rotating_radius_km":old_rot,
        "rns_gr_fixed_mass_rotating_radius_km":gr_rot,
        "f30_minus_rns_rotating_radius_km":total,
        "f30_static_curve_radius_at_target_mass_km":old_static,
        "rns_gr_static_radius_at_target_mass_km":gr_static,
        "f30_static_curve_minus_rns_static_km":source_static_offset,
        "f30_empirical_rotating_minus_f30_static_at_same_MG_km":old_corr,
        "rns_rotating_minus_static_at_same_MG_km":gr_corr,
        "difference_of_rotation_corrections_at_same_MG_km":old_corr-gr_corr,
        "f30_empirical_reference_static_mass_msun":float(fit["M_static_Msun"]),
        "f30_empirical_reference_mass_shift_msun":float(fit["mass_shift_Msun"]),
        "rns_print_resolution_km":0.01,
        "diagnostic_warning":"Static knots are limited resolution, F30 fit was calibrated to same baryon mass while comparison fixes gravitational mass; not an EOS likelihood or posterior.",
    }


def audit(knots:dict, gr:dict)->dict:
    if (set(knots)!=set(EOS) or set(gr.get("eos",{}))!=set(EOS) or
            gr.get("status")!="ALL_SEVEN_VALIDATED" or
            gr.get("validated_eos_count")!=7 or
            not math.isclose(float(gr.get("target_gravitational_mass_msun",0)),EXPECTED_MASS,abs_tol=1e-9) or
            not math.isclose(float(gr.get("spin_hz",0)),EXPECTED_SPIN,abs_tol=1e-8)):
        raise ValueError("F30 knots and RNS source identities, mass, or spin do not match")
    rows={name:compare_curve(knots[name],gr["eos"][name],EXPECTED_MASS,EXPECTED_SPIN)
          for name in EOS}
    residuals=np.array([rows[name]["f30_minus_rns_rotating_radius_km"] for name in EOS])
    return {
        "schema":"j0740-f30-empirical-vs-rns-full-gr-radius-at-fixed-mass-v1",
        "status":"SEVEN_EOS_EMPIRICAL_VS_RNS_GR_RADIUS_SENSITIVITY_MEASURED_NOT_EVIDENCE",
        "EOS_count":7,
        "reference_mass_msun":EXPECTED_MASS,
        "reference_spin_hz":EXPECTED_SPIN,
        "rns_evidence_workflow_run":RNS_SOURCE_RUN,
        "rns_evidence_json_sha256":RNS_JSON_SHA256,
        "f30_static_knots_json_sha256":KNOTS_SHA256,
        "all_empirical_radii_above_gr":bool(np.all(residuals>0)),
        "min_f30_minus_gr_radius_km":float(np.min(residuals)),
        "max_f30_minus_gr_radius_km":float(np.max(residuals)),
        "method":"F30 published Suleimanov2020 approximate same-baryon rotation forward fit over cached JESTER static knots; full GR RNS run at 346.536369 Hz and 2.073 solar mass; static-basis discrepancies decomposed exactly",
        "limits":["No posterior, EOS Bayes factor, or direct photon likelihood computed",
                  "RNS stdout precision is 0.01 km and 0.001 solar mass",
                  "F30 reference static knots limited resolution; individual differences include static source-vs-RNS solver difference",
                  "Rotation fit is calibrated to same baryon mass; equality imposed on final gravitational mass, not reference baryon mass",
                  "Only one target gravitational mass is checked, not an integrated mass or EOS population prior"],
        "eos":rows,
    }


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-knots",required=True,type=Path)
    parser.add_argument("--rns-json",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args()
    verify_bytes(args.source_knots,KNOTS_SHA256)
    verify_bytes(args.rns_json,RNS_JSON_SHA256)
    result=audit(json.loads(args.source_knots.read_text()),json.loads(args.rns_json.read_text()))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    for name,row in result["eos"].items():
        print(f"{name:8s} F30={row['f30_empirical_fit_rotating_radius_km']:.6f}km GR={row['rns_gr_fixed_mass_rotating_radius_km']:.2f}km residual={row['f30_minus_rns_rotating_radius_km']:+.4f}km static_offset={row['f30_static_curve_minus_rns_static_km']:+.4f}km")
    print("STATUS",result["status"],"RANGE",result["min_f30_minus_gr_radius_km"],result["max_f30_minus_gr_radius_km"])


if __name__=="__main__":
    main()
