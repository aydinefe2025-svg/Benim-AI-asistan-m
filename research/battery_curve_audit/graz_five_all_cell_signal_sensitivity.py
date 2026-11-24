"""Graz 5 original physical cells: same-cell source sample-nearest time audits.

Extends already-merged PR #822 two-cell alignment without repeating it as new
cells. Exactly ONE official source ZIP, verified DOI/MD5/CRC before decoding.
Per-file time joins at 0.5, 1.0 and 2.5 seconds, no cross-cell joins.
No assumption that clock alignment implies same protocol stage, true sensor
calibration, capacity loss, dynamic impact, or causal effect of static preload.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import statistics
import zipfile
from pathlib import Path

from research.battery_curve_audit import graz_source_preflight as source
from research.battery_curve_audit import graz_signal_alignment as alignment
from research.battery_curve_audit import graz_five_sp_full_row_profile as profile

GOAL = "graz-20261123-all-five-original-sample-time-proximity-three-thresholds"
TOLERANCES = (0.5, 1.0, 2.5)
EXPECTED_CELLS = ("01", "02", "03", "04", "05")
EXPECTED_ELECTRICAL = {"01":253861, "02":207383, "03":210541, "04":209558, "05":209994}
EXPECTED_SP_COUNTS = {"01":46816, "02":46855, "03":46873, "04":46683, "05":46794}


def nearest_summary(electrical: list, sensor: list) -> dict:
    """Reuses certified source-parse joins; tolerance changes are explicit."""
    if not electrical or not sensor:
        raise ValueError("empty original instrument signal")
    results = {}
    for threshold in TOLERANCES:
        result = alignment.pair_samples(electrical, sensor, tolerance_s=threshold)
        if result["matched_sp_samples"] + result["unmatched_sp_samples"] != len(sensor):
            raise ValueError("sample accounting mismatch")
        if result["ambiguous_matches"] > result["unmatched_sp_samples"]:
            raise ValueError("ambiguous tie accounting impossible")
        results[str(threshold)] = {
            "matched_sp_rows": result["matched_sp_samples"],
            "unmatched_sp_rows": result["unmatched_sp_samples"],
            "ambiguous_device_conflict_ties": result["ambiguous_matches"],
            "median_absolute_timestamp_offset_s": result["median_abs_time_error_s"],
            "maximum_absolute_timestamp_offset_s": result.get("max_abs_time_error_s"),
            "matched_current_sign_counts": result["sampled_current_sign_counts"],
        }
    counts = [results[str(t)]["matched_sp_rows"] for t in TOLERANCES]
    if counts != sorted(counts):
        raise ValueError("broader tolerance matched fewer source rows")
    return results


def inspect(blob: bytes, publisher_size: int) -> dict:
    verified = source.inspect_archive(blob, publisher_size)
    if verified["source_doi"] != source.DOI or verified["original_zip_sha256"] != hashlib.sha256(blob).hexdigest():
        raise ValueError("source provenance lost")
    if not verified["publisher_zip_md5_verified"] or not verified["zip_crc_verified"]:
        raise ValueError("official raw source verification failed")
    results = {}
    total_electric, total_sp = 0, 0
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members = z.infolist()
        for cell in EXPECTED_CELLS:
            own = [m for m in members if not m.is_dir() and source.explicit_cell_in_path(m.filename) == cell]
            e_files = [m for m in own if source.role_for_member(m.filename) == "charge_discharge_log_candidate"]
            sp_files = [m for m in own if source.role_for_member(m.filename) == "thickness_sp_candidate"]
            if len(e_files) != 1 or len(sp_files) != 3:
                raise ValueError("wrong original member count for physical cell " + cell)
            electrical = alignment.log_samples(z, e_files[0])
            if len(electrical) != EXPECTED_ELECTRICAL[cell]:
                raise ValueError("original electrical row count drift in " + cell)
            total_electric += len(electrical)
            sp_out = []
            for file in sorted(sp_files, key=lambda m: m.filename):
                rows, sp_start_epoch = alignment.sp_samples(z, file)
                if not rows:
                    raise ValueError("missing measured SP data")
                match = nearest_summary(electrical, rows)
                sp_out.append({
                    "sp_original_member": file.filename,
                    "same_physical_publisher_folder_id": cell,
                    "source_preload_kN": source.CELL_PRELOAD_KN[cell],
                    "original_sp_numeric_rows": len(rows),
                    "original_sp_start_epoch_seconds": sp_start_epoch,
                    "original_sp_last_epoch_seconds": rows[-1][0],
                    "original_electrical_first_epoch_seconds": electrical[0][0],
                    "original_electrical_last_epoch_seconds": electrical[-1][0],
                    "match_tolerance_comparison_s": match,
                    "same_protocol_step_proven": False,
                    "independent_interdevice_clock_calibration_proven": False,
                })
                total_sp += len(rows)
            actual_sp = sum(p["original_sp_numeric_rows"] for p in sp_out)
            if actual_sp != EXPECTED_SP_COUNTS[cell]:
                raise ValueError("SP original source row count drift in " + cell)
            results[cell] = {
                "publisher_declared_static_preload_kN":source.CELL_PRELOAD_KN[cell],
                "original_electrical_member":e_files[0].filename,
                "electric_source_rows":len(electrical),
                "sp_files":sp_out,
                "source_folder_verified_from_publisher_zip":True,
                "not_interchangeable_with_other_cell_ids":True,
            }
    if total_electric != 1091337 or total_sp != 234021:
        raise ValueError("original five-cell source population not preserved")
    if len({p["sp_original_member"] for x in results.values() for p in x["sp_files"]}) != 15:
        raise ValueError("duplicate original SP path")
    totals = {
        str(t): sum(f["match_tolerance_comparison_s"][str(t)]["matched_sp_rows"]
                    for c in results.values() for f in c["sp_files"])
        for t in TOLERANCES
    }
    original_02_03 = sum(f["match_tolerance_comparison_s"]["2.5"]["matched_sp_rows"]
                         for cell in ("02", "03") for f in results[cell]["sp_files"])
    # The existing independently approved 02/03 source analysis (#822)
    # is a regression baseline. Never label its samples as additional cells.
    if original_02_03 != 64380:
        raise ValueError("real original 02/03 matched-source regression changed")
    for cell in EXPECTED_CELLS:
        for f in results[cell]["sp_files"]:
            if cell == "03" and ("09_09_2025" in f["sp_original_member"] or "10_09_2025" in f["sp_original_member"]):
                if f["match_tolerance_comparison_s"]["2.5"]["matched_sp_rows"] != 0:
                    raise ValueError("out-of-window cell03 SP data incorrectly paired")
    return {
        "goal_key": GOAL,
        "source_doi":source.DOI,
        "official_source_md5":source.OFFICIAL_MD5,
        "official_source_sha256":verified["original_zip_sha256"],
        "source_original_bytes":publisher_size,
        "original_archive_crc_pass":True,
        "original_electrical_rows":total_electric,
        "original_sp_sensor_rows":total_sp,
        "same_physical_source_folders":len(results),
        "sp_file_count":15,
        "per_tolerance_sp_rows_with_nearest_electrical_timestamp":totals,
        "previous_source_02_03_2p5_second_regression_rows":original_02_03,
        "remaining_unmatched_2p5_s":total_sp-totals["2.5"],
        "cells":results,
        "units_note":"Published SP sensor positions are micro-m; electrical Current original header does not state amperes. Source static load is a separate nominal experiment condition.",
        "time_standard":"Vienna-local original instrument time stamps to UTC by Europe/Vienna 2024-2025 source-era DST rule; clocks were not calibrated against each other",
        "guardrails":{
            "cross_source_cell_ids_never_joined":True,
            "independent_instrument_clock_calibration_verified":False,
            "electrical_charge_discharge_protocol_phase_verified":False,
            "sensor_absolute_force_calibration_verified":False,
            "calibrated_battery_capacity_or_soh_reconstructed":False,
            "causal_load_effect_proven":False,
            "dynamic_impact_measured":False,
            "separate_four_cell_graz_archive_join_verified":False,
            "measured_field_false_match_rate":None
        }
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    blob, size = source.get_original()
    result = inspect(blob, size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    for cell,x in result["cells"].items():
        print("ORIGINAL_FIVE_CELL_TIMESTAMP_JOIN",cell,x["electric_source_rows"],
              [y["match_tolerance_comparison_s"]["2.5"]["matched_sp_rows"] for y in x["sp_files"]],flush=True)
    print("REAL_5CELL_MATCH_SENSITIVITY",result["per_tolerance_sp_rows_with_nearest_electrical_timestamp"],
          "previous 02+03",result["previous_source_02_03_2p5_second_regression_rows"],flush=True)
    print("NOT_EXACT_PROTOCOL_OR_PHYSICAL_CAUSALITY",flush=True)


if __name__ == "__main__":
    main()
