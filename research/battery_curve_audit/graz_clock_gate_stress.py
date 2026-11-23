"""Reproducible V3 *synthetic* clock-evidence adversarial Monte Carlo.

This does not reprocess any Graz physical recordings, provide lab trust roots,
validate electrode electrochemistry, certify a real device, or release production.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from research.battery_curve_audit import graz_virtual_lab as v
from research.battery_curve_audit import graz_clock_anchor_gate as gate

SCENARIOS=(
    "nominal_signed_two_root", "electrical_dropout_20pct", "electrical_dropout_60pct",
    "false_attestation_3second_offset", "clock_missing_anchors", "clock_tampered_anchor",
    "clock_anchor_replay", "clock_single_witness", "clock_shared_issuer_key",
    "clock_400ppm_drift", "phase_provenance_missing", "physical_cell_spoof",
    "phase_spoof", "witness_uncertainty_too_high",
)
EXPECTED_ZERO_ACCEPT={
    "false_attestation_3second_offset", "clock_missing_anchors", "clock_tampered_anchor",
    "clock_anchor_replay", "clock_single_witness", "clock_shared_issuer_key",
    "clock_400ppm_drift", "phase_provenance_missing", "physical_cell_spoof",
    "phase_spoof", "witness_uncertainty_too_high",
}


def run(seed_start:int=20261123,seeds:int=12)->dict:
    if not isinstance(seeds,int) or isinstance(seeds,bool) or not 1<=seeds<=200:
        raise ValueError("bounded seeds required")
    scenarios=[]
    for case in SCENARIOS:
        stat={"scenario":case,"synthetic_samples":0,"accepted":0,"wrong_time_accepted":0,
              "correct_virtual_time":0,"rejected_before_join":0,
              "successful_two_root_gates":0,"denied_gates":0,"physical_cells_tested":len(v.PRELOADS_KN)}
        denied_reasons={}
        for seed in range(seed_start,seed_start+seeds):
            for cell,preload in v.PRELOADS_KN.items():
                offset=3.0 if case=="false_attestation_3second_offset" else .2
                drop=.2 if case=="electrical_dropout_20pct" else (.6 if case=="electrical_dropout_60pct" else .05)
                # distinct random series for all five virtual physical source identities
                base_seed=seed+int(cell)*100000
                e,s=v.generate_synthetic(cell,base_seed,preload_kN=preload,
                             clock_offset_s=offset,electric_drop=drop,
                             stage_id_valid=case!="phase_spoof",
                             cell_id_valid=case!="physical_cell_spoof")
                session_id=f"SYN-V3-{seed}-{cell}"
                drift=400.0 if case=="clock_400ppm_drift" else 0.0
                if drift:
                    s=[replace(x,observed_t=x.observed_t + drift*1e-6*(x.truth_t-s[0].truth_t)) for x in s]
                proof,roots=gate.mock_independent_witnesses(seed=base_seed,session_id=session_id,
                                  cell_id=cell,truth_first_t=s[0].truth_t,
                                  clock_offset_s=offset,drift_ppm=drift,
                                  issued_for_wrong_session=case=="clock_anchor_replay",
                                  tamper_after_sign=case=="clock_tampered_anchor",
                                  omit_second_root=case=="clock_single_witness")
                if case=="clock_missing_anchors":proof=[]
                elif case=="clock_shared_issuer_key":
                    roots={root:next(iter(roots.values())) for root in roots}
                elif case=="witness_uncertainty_too_high":
                    # Invalid even if re-signed: > 0.05s independent uncertainty budget.
                    first=replace(proof[0],uncertainty_s=.5,mac_hex="")
                    proof[0]=gate.sign_anchor(first,signing_key=roots[first.issuer])
                result=gate.verify_and_join(e,s,anchors=proof,trust_roots=roots,
                      session_id=session_id,expected_cell=cell,
                      true_reference_bounds=(s[0].truth_t,s[0].truth_t+1200.),
                      phase_source_authentic=case!="phase_provenance_missing")
                stat["synthetic_samples"]+=len(s)
                stat["accepted"]+=result["accepted"]
                stat["wrong_time_accepted"]+=result["wrong_time_accepted"]
                stat["correct_virtual_time"]+=result.get("ground_truth_correct",0)
                stat["rejected_before_join"]+=result["rejected_before_join"]
                stat["successful_two_root_gates"]+=int(result["gate_passed"])
                stat["denied_gates"]+=int(not result["gate_passed"])
                if not result["gate_passed"]:
                    denied_reasons[result["gate_reason"]]=denied_reasons.get(result["gate_reason"],0)+1
        stat["denial_reasons"]={key:denied_reasons[key] for key in sorted(denied_reasons)}
        stat["simulated_wrong_accept_fraction"]=(stat["wrong_time_accepted"]/stat["accepted"] if stat["accepted"] else None)
        assert stat["synthetic_samples"]==seeds*len(v.PRELOADS_KN)*240
        if case in EXPECTED_ZERO_ACCEPT:
            assert stat["accepted"]==0 and stat["wrong_time_accepted"]==0,(case,stat)
        else:
            assert stat["accepted"]>0 and stat["wrong_time_accepted"]==0,(case,stat)
        scenarios.append(stat)
    return {
        "goal_key":"graz-20261123-independent-two-root-clock-evidence-simulation-v3",
        "study":"CANO Graz five-cell independent-clock witness adversarial simulation",
        "simulation_only":True,
        "source_reference_only":{"source_doi":v.RECORD_DOI,
              "publisher_zip_sha256":v.REAL_SOURCE_SHA256,
              "real_original_five_electrical_rows":v.REAL_SOURCE_SUMMARY["five_original_electrical_rows"],
              "real_original_five_sp_rows":v.REAL_SOURCE_SUMMARY["five_original_sp_rows"],
              "real_original_within_1s_matches":v.REAL_SOURCE_SUMMARY["five_source_matches_within_one_second"]},
        "real_source_data_downloaded":False,
        "hardware_trusted_roots_available":False,
        "ground_truth_only_in_virtual_world":True,
        "test_root_protection":"simulated independent 256-bit HMAC keys, NEVER actual device trust anchors",
        "seed_start":seed_start,"seeds_per_scenario":seeds,
        "physical_id_strings_in_simulation":list(v.PRELOADS_KN),
        "preload_kN_labels_reference_only":v.PRELOADS_KN,
        "scenarios":scenarios,
        "source_clocks_independently_calibrated":False,
        "sensor_calibration_verified":False,
        "independent_real_phase_metadata_verified":False,
        "real_capacity_ah_verified":False,
        "real_fea_mechanics_verified":False,
        "dynamic_impact_verified":False,
        "physical_production_release_allowed":False,
        "unresolved_threats":["real independent trust roots/protected calibration not supplied",
              "both reference witnesses compromised or sharing an unknown time source",
              "signed anchors may not be bound to actual real sensor/electrical samples",
              "actual battery test protocol stage/authenticated units are unavailable",
              "simulation cannot certify physical material/thermal/electrochemical response"],
    }


def main():
    a=argparse.ArgumentParser()
    a.add_argument("out",type=Path);a.add_argument("--seeds",type=int,default=12)
    args=a.parse_args()
    data=run(seeds=args.seeds)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(data,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)+"\n"
    args.out.write_text(raw,encoding="utf-8")
    print("SIMULATION_ONLY",len(data["scenarios"]),"attack/acceptance scenarios",
          sum(x["synthetic_samples"] for x in data["scenarios"]),"synthetic records")
    for x in data["scenarios"]:
        print(x["scenario"],"admitted",x["accepted"],"wrong_virtual_time",x["wrong_time_accepted"],
              "evidence_denials",x["denied_gates"])
    print("REAL_HARDWARE_CALIBRATION_AND_PRODUCTION_BLOCKED")
    print("SHA256",hashlib.sha256(raw.encode()).hexdigest())

if __name__=="__main__":main()