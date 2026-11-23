"""Real-source timestamp clock-offset identifiability challenge, NOT a clock calibration.

Uses only source-authenticated ORIGINAL Graz five-cell electrical and SP traces.
Artificially shifts genuine SP timestamps by ±1–3 seconds without changing
measured channels to see whether nearest-timestamp matching can identify
a clock offset. Such shifts are COUNTERFACTUAL and not a measured device error.
Checks pre-existing genuine source totals; does not count more observations.
"""
from __future__ import annotations
import argparse
import bisect
import hashlib
import io
import json
import zipfile
from pathlib import Path

from research.battery_curve_audit import graz_source_preflight as source
from research.battery_curve_audit import graz_signal_alignment as original

GOAL_KEY = "graz-20261123-real-source-counterfactual-clock-offset-identifiability"
CELLS = ("01", "02", "03", "04", "05")
OFFSETS_S = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0)
TOLERANCES_S = (0.5, 1.0)
ORIGINAL_ELECTRICAL_COUNTS = {"01":253861, "02":207383, "03":210541, "04":209558, "05":209994}
ORIGINAL_SP_COUNTS = {"01":46816, "02":46855, "03":46873, "04":46683, "05":46794}


def match_counterfactual(
    electrical: list[tuple[float, str, float, float]],
    sp: list[tuple[float, float, float, float]],
    shifted_seconds: float,
    tolerance_s: float,
) -> dict:
    """Only closest timestamp, with same exclusion rule for device-conflicted ties."""
    if shifted_seconds not in OFFSETS_S or tolerance_s not in TOLERANCES_S:
        raise ValueError("an unregistered shift or threshold cannot be treated as experimental proof")
    if not electrical or not sp:
        raise ValueError("empty source trace cannot be used to infer clock")
    stamps = [row[0] for row in electrical]
    if stamps != sorted(stamps) or len(set(stamps)) < 2:
        raise ValueError("original electrical timestamps not monotonic/distinct")
    matched=ties=0
    for row in sp:
        shifted = row[0] + shifted_seconds
        i = bisect.bisect_left(stamps, shifted)
        candidates = [(abs(stamps[j] - shifted), j) for j in (i-1, i) if 0 <= j < len(stamps)]
        candidates.sort()
        if not candidates or candidates[0][0] > tolerance_s:
            continue
        if (len(candidates) > 1
            and abs(candidates[1][0] - candidates[0][0]) < 1e-6
            and electrical[candidates[0][1]][1:] != electrical[candidates[1][1]][1:]):
            ties += 1
            continue
        matched += 1
    return {"counterfactual_shift_s":shifted_seconds, "threshold_s":tolerance_s,
            "genuine_sp_source_rows":len(sp), "time_only_matches":matched,
            "rejected_conflicting_device_ties":ties,
            "unmatched_sp_rows":len(sp)-matched,
            "these_shifts_are_not_observed_clock_offsets":True}


def inspect_original(blob: bytes, expected_size: int) -> dict:
    provenance = source.inspect_archive(blob, expected_size)
    if provenance["source_doi"] != "10.5281/zenodo.22079387":
        raise ValueError("wrong physical source DOI")
    if (not provenance["publisher_zip_md5_verified"]
        or not provenance["zip_crc_verified"]
        or provenance["original_zip_sha256"] != hashlib.sha256(blob).hexdigest()):
        raise ValueError("original Zenodo source authenticity gate failed")

    by_cell = {}
    totals = {str(t): {str(offset):0 for offset in OFFSETS_S}
              for t in TOLERANCES_S}
    electrical_rows = sp_rows = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members=z.infolist()
        for cell in CELLS:
            cell_files=[m for m in members if not m.is_dir()
                and source.explicit_cell_in_path(m.filename)==cell]
            electric_files=[m for m in cell_files
                if source.role_for_member(m.filename)=="charge_discharge_log_candidate"]
            sp_files=[m for m in cell_files
                if source.role_for_member(m.filename)=="thickness_sp_candidate"]
            if len(electric_files)!=1 or len(sp_files)!=3:
                raise ValueError("expected 1 original electrical and 3 SP per physical cell")
            electric=original.log_samples(z,electric_files[0])
            if len(electric)!=ORIGINAL_ELECTRICAL_COUNTS[cell]:
                raise ValueError("source original electrical count drift in "+cell)
            electrical_rows+=len(electric)
            series=[]
            cell_sp_rows=0
            for sp_file in sorted(sp_files,key=lambda m:m.filename):
                sp,sp_epoch=original.sp_samples(z,sp_file)
                cell_sp_rows+=len(sp)
                rows = {str(t):{} for t in TOLERANCES_S}
                for threshold in TOLERANCES_S:
                    for offset in OFFSETS_S:
                        summary = match_counterfactual(electric,sp,offset,threshold)
                        rows[str(threshold)][str(offset)]=summary
                        totals[str(threshold)][str(offset)]+=summary["time_only_matches"]
                series.append({
                    "same_cell_original_physical_id":cell,
                    "sp_source_member":sp_file.filename,
                    "source_sp_start_epoch":sp_epoch,
                    "source_sp_rows":len(sp),
                    "clock_offset_counterfactual_time_only_matches":rows,
                    "laboratory_instrument_clock_synchronization_proven":False,
                })
            if cell_sp_rows!=ORIGINAL_SP_COUNTS[cell]:
                raise ValueError("SP source count drift in "+cell)
            sp_rows+=cell_sp_rows
            by_cell[cell]={"original_source_electrical_rows":len(electric),
                          "original_source_sp_rows":cell_sp_rows,
                          "publisher_nominal_preload_kN":source.CELL_PRELOAD_KN[cell],
                          "sp_source_files":series}
    if electrical_rows!=1091337 or sp_rows!=234021:
        raise ValueError("whole authentic five-cell source population mismatch")
    if totals["0.5"]["0.0"]!=182225 or totals["1.0"]["0.0"]!=204673:
        raise ValueError("zero shift does not reproduce merged independently accepted real data")
    if sum(
         f["clock_offset_counterfactual_time_only_matches"]["1.0"]["0.0"]["time_only_matches"]
         for cell in ("02","03") for f in by_cell[cell]["sp_source_files"]
       )!=64380:
        raise ValueError("02/03 accepted-source regression mismatch")
    for f in by_cell["03"]["sp_source_files"]:
        if "09_09_2025" in f["sp_source_member"] or "10_09_2025" in f["sp_source_member"]:
            if any(f["clock_offset_counterfactual_time_only_matches"]["1.0"][str(s)]["time_only_matches"]
                   for s in OFFSETS_S):
                raise ValueError("out-of-window SP recordings joined under artificial clock shift")
    return {
        "goal_key":GOAL_KEY,
        "original_source_doi":source.DOI,
        "source_zip_sha256":provenance["original_zip_sha256"],
        "publisher_pinned_md5":source.OFFICIAL_MD5,
        "official_zip_crc_and_byte_count_verified":True,
        "physical_source_cells":5,
        "original_electrical_source_rows":electrical_rows,
        "original_sp_sensor_source_rows":sp_rows,
        "offsets_s_tested_are_deliberately_counterfactual":list(OFFSETS_S),
        "nearest_match_tolerances_s":list(TOLERANCES_S),
        "source_zero_shift_baseline_reconfirmed":True,
        "match_counts_by_tolerance_and_counterfactual_offset":totals,
        "cells":by_cell,
        "scope_and_safety":{
            "the_shifted_SP_timestamps_are_observed_sensor_clock_errors":False,
            "physical_instrument_clock_offset_identified":False,
            "independent_reference_clock_available":False,
            "original_charge_discharge_controller_stage_labels_verified":False,
            "source_current_column_absolute_ampere_unit_verified":False,
            "electrochemical_capacity_or_SOH_reconstructed":False,
            "physical_sensor_or_force_calibration_verified":False,
            "dynamic_impact_tested":False,
            "mechanical_preload_causal_effect_established":False,
            "field_false_positive_rate_measured":False,
            "cross_cell_or_older_Graz_source_joined":False,
        }
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("output",type=Path)
    args=ap.parse_args()
    blob,size=source.get_original()
    r=inspect_original(blob,size)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(r,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("GRAZ_ORIGINAL_SOURCE_5_CELL_REAL_TIMESTAMPS",r["original_electrical_source_rows"],r["original_sp_sensor_source_rows"])
    print("GRAZ_COUNTERFACTUAL_CLOCK_OFFSET_COUNTS",r["match_counts_by_tolerance_and_counterfactual_offset"])
    print("NOT_VALIDATED_CLOCK_OFFSET_OR_PHYSICAL_CAUSAL_EFFECT",flush=True)


if __name__=="__main__":
    main()
