"""Independent reproducibility of three *new* real Bayreuth 2025 source cells.

The upstream originals are public CC BY 4.0: DOI 10.5281/zenodo.15755725.
This module REUSES the previously unit-tested genuine source parsing, segmented
I*dt integration and multi-waveform homologous plan-line guard from PR #795.
Only pinned new F0007, F0022 and F0138 originals are downloaded. This does not
certify calibration, causality or the full 48-cell population.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import zipfile
from pathlib import Path
from research.battery_curve_audit import bayreuth_two_cell_independent_integral as core

ADDITIONAL_SOURCE_FILES = {
    "F0007": {"size": 18993991, "md5": "e3357a887d4816c391a08e8f980c9d5d"},
    "F0022": {"size": 18603441, "md5": "1dbda5a8194f7d8cbfac99a5510d93a4"},
    "F0138": {"size": 17152373, "md5": "275e64c8061dec28295c88ed0d495995"},
}

@contextmanager
def registered_original(cell: str, spec: dict):
    """Scope a new pinned source to the already-validated original verifier.

    This script and its CI job are single-threaded and use a new Python process;
    the temporary registration is undone even for invalid or corrupt inputs.
    """
    if cell in core.SOURCE_FILES:
        raise ValueError("new cell must not overwrite a previously pinned original")
    if set(spec) != {"size", "md5"} or spec["size"] <= 0 or len(spec["md5"]) != 32:
        raise ValueError("missing pinned official size/MD5")
    core.SOURCE_FILES[cell] = dict(spec)
    try:
        yield
    finally:
        del core.SOURCE_FILES[cell]


def fetch_additional_original(cell: str) -> bytes:
    if cell not in ADDITIONAL_SOURCE_FILES:
        raise ValueError("new source is not on the verified publisher manifest")
    with registered_original(cell, ADDITIONAL_SOURCE_FILES[cell]):
        return core.fetch_publisher(cell)


def analyze_original_blob(cell: str, content: bytes, spec: dict) -> dict:
    """Verify EXACT source bytes and calculate actual BoL/EoL measured I*dt."""
    with registered_original(cell, spec):
        core.validate_zip(content, cell)
    with zipfile.ZipFile(io.BytesIO(content)) as arc:
        checkups = {}
        for stage, filename in (("beginning", "m0001_checkup.txt"), ("ending", "m0003_checkup.txt")):
            matches = [m.filename for m in arc.infolist() if m.filename.lower().endswith(filename)]
            if len(matches) != 1:
                raise ValueError("original source checkup missing or non-unique")
            checkups[stage] = core.scan_checkup(arc, matches[0])
    alignment = core.infer_stage_line_offset(checkups["beginning"], checkups["ending"])
    paired = {}
    for phase in ("discharge", "charge"):
        matched = (core.select_matched_source_step(checkups["beginning"], checkups["ending"], phase,
                     alignment["beginning_minus_ending_plan_line_offset"])
                   if alignment.get("offset_inferred") else None)
        if matched is None:
            paired[phase] = {
                "comparable": False,
                "reason": "published reference checkups lacked enough homologous steps: do not invent a numeric change",
            }
            continue
        a,b = matched
        native_mAh = (b["source_peak_Ah_Step_abs_Ah"] - a["source_peak_Ah_Step_abs_Ah"]) * 1000
        integral_mAh = (b["integral_trapezoid_Ah"] - a["integral_trapezoid_Ah"]) * 1000
        paired[phase] = {
            "comparable_homologous_source_step": True,
            "beginning_plan_line": a["plan_line"], "ending_plan_line": b["plan_line"],
            "native_Ah_Step_delta_mAh": native_mAh,
            "source_step_delta_mAh": native_mAh,
            "independently_integrated_trapezoid_delta_mAh": integral_mAh,
            "independently_integrated_right_delta_mAh": (b["integral_right_Ah"]-a["integral_right_Ah"])*1000,
            "difference_of_delta_mAh": integral_mAh - native_mAh,
            "source_BoL_step_mAh": a["source_peak_Ah_Step_abs_Ah"]*1000,
            "source_EoL_step_mAh": b["source_peak_Ah_Step_abs_Ah"]*1000,
            "percent_change_in_this_single_step": native_mAh/(a["source_peak_Ah_Step_abs_Ah"]*10),
            "initial_endpoint_V": a["last_measured_voltage_V"],
            "ending_endpoint_V": b["last_measured_voltage_V"],
            "not_a_certified_capacity_loss": True,
            "original_test_program_not_available": True,
            "same_sensor_calibration_not_independently_checked": True,
        }
    return {
        "original_id": cell,
        "source_bytes": len(content),
        "source_official_md5": spec["md5"],
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "zip_crc_pass": True,
        "original_checkups": checkups,
        "stage_line_offset_alignment": alignment,
        "paired_measurement": paired,
        "not_a_new_physical_measurement": True,
    }


def analyze_additions(data: dict[str, bytes]) -> dict:
    if set(data) != set(ADDITIONAL_SOURCE_FILES):
        raise ValueError("must verify every and only three pinned new original physical cells")
    cells = {cell: analyze_original_blob(cell,data[cell],ADDITIONAL_SOURCE_FILES[cell]) for cell in ADDITIONAL_SOURCE_FILES}
    return {
        "source_doi": core.RECORD_DOI,
        "license": "CC BY 4.0",
        "prior_validated_source_cells_in_distinct_merged_PR_795": ["F0001", "F0002"],
        "new_independent_source_cell_count": len(cells),
        "new_cell_ids": list(cells),
        "distinct_source_cell_count_across_previous_and_this_audit": 2+len(cells),
        "original_new_checkup_numeric_rows": sum(x["rows_parsed"] for d in cells.values() for x in d["original_checkups"].values()),
        "new_comparable_discharge_cell_count": sum(bool(q["paired_measurement"]["discharge"].get("comparable_homologous_source_step")) for q in cells.values()),
        "new_comparable_charge_cell_count": sum(bool(q["paired_measurement"]["charge"].get("comparable_homologous_source_step")) for q in cells.values()),
        "cells": cells,
        "integration": "original native BaSyTec I[A] * Time[h], within observed same Line/Command/Cyc-Count step; no extrapolation",
        "instrument_calibration_not_verified": True,
        "not_full_48_cell_population": True,
        "same_cells_as_Stroebl": False,
        "quantifies_aging_causality": False,
        "no_original_full_testplan_pln": True,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("output", type=Path)
    args = p.parse_args()
    originals = {cell: fetch_additional_original(cell) for cell in ADDITIONAL_SOURCE_FILES}
    result = analyze_additions(originals)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    for cell in result["new_cell_ids"]:
        q=result["cells"][cell]
        print("BAYREUTH_NEW_ORIGINAL_MD5_CRC_PASS",cell,q["source_bytes"],q["source_official_md5"])
        for kind,z in q["paired_measurement"].items():
            print("CONTROL_STEP",cell,kind,"matched",bool(z.get("comparable_homologous_source_step")),
                  "native_mAh",z.get("source_step_delta_mAh"),"integral_mAh",z.get("independently_integrated_trapezoid_delta_mAh"))
    print("REAL_PHYSICAL_CELL_SCOPE",result["new_independent_source_cell_count"],"new and",result["distinct_source_cell_count_across_previous_and_this_audit"],"total; NOT historical calibration")

if __name__ == '__main__':
    main()