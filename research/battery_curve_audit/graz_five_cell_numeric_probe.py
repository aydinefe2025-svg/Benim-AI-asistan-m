"""Independent field-level scan of the genuine five-cell Graz cycling logs.

Source DOI 10.5281/zenodo.22079387. Does NOT claim measured capacity,
SP time alignment, force calibration, impact response, or causal preload effect.
A conditional 'Current numeric x seconds' sum is arithmetic only: the field
header has no unit, so this is NOT certified Ah or capacity.
"""
from __future__ import annotations
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import math
import pathlib
import re
import urllib.request
import zipfile

from research.battery_curve_audit import graz_five_cell_original_preflight as core

GOAL_KEY = "graz-20261123-five-real-cycling-log-time-current-probe"
CELL_RE = re.compile(r"/Fresh cell (0[1-5])/")
MAX_NON_GAP_DT_SECONDS = 120.0


def filename_groups(members) -> dict[str, dict[str, list[str]]]:
    groups = {cell: {"cycling_log": [], "sp_txt": []} for cell in core.PUBLISHER_CELLS}
    for info in members:
        if info.is_dir():
            continue
        name = info.filename
        m = CELL_RE.search(name)
        if not m:
            continue
        cell = m.group(1)
        if name.lower().endswith(".log"):
            groups[cell]["cycling_log"].append(name)
        elif pathlib.PurePosixPath(name).name.lower().startswith("sp_") and name.lower().endswith("_logfile.txt"):
            groups[cell]["sp_txt"].append(name)
        else:
            raise ValueError("unclassified cell-source file: " + cell)
    for cell, g in groups.items():
        if len(g["cycling_log"]) != 1 or len(g["sp_txt"]) != 3:
            raise ValueError("not exactly one electrical + three SP logs in " + cell)
    return groups


def parse_timestamp(value: str) -> dt.datetime:
    return dt.datetime.strptime(value.strip(), "%Y-%m-%d_%H-%M-%S-%f")


def scan_electrical_log(z: zipfile.ZipFile, name: str) -> dict:
    counters = collections.Counter()
    first, last, prev_t, prev_current = None, None, None, None
    vmin, vmax, imin, imax = None, None, None, None
    trap_numsec, right_numsec = 0.0, 0.0
    devices = set()
    with z.open(name, "r") as f:
        with io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.DictReader(stream, skipinitialspace=True)
            header = [x.strip() for x in reader.fieldnames or []]
            if header != ["Time", "Device", "Voltage", "Current", "Power"]:
                raise ValueError("unexpected original electrical column schema: " + repr(header))
            for row in reader:
                counters["data_rows_seen"] += 1
                try:
                    when = parse_timestamp(row["Time"])
                    voltage = float(row["Voltage"].strip())
                    current = float(row["Current"].strip())
                    power = float(row["Power"].strip())
                    if not all(map(math.isfinite, (voltage, current, power))):
                        raise ValueError("nonfinite numeric")
                    if abs(voltage) > 1000 or abs(current) > 5000 or abs(power) > 100000:
                        raise ValueError("numeric outside scanner plausibility cap")
                except (ValueError, TypeError, KeyError, AttributeError):
                    counters["rows_unparseable"] += 1
                    continue
                counters["numeric_timestamp_rows"] += 1
                if first is None:
                    first = when
                last = when
                vmin, vmax = (voltage if vmin is None else min(vmin, voltage)), (voltage if vmax is None else max(vmax, voltage))
                imin, imax = (current if imin is None else min(imin, current)), (current if imax is None else max(imax, current))
                if len(devices) < 20 and row.get("Device"):
                    devices.add(row["Device"].strip())
                if prev_t is not None:
                    elapsed = (when - prev_t).total_seconds()
                    if elapsed <= 0:
                        counters["nonpositive_time_steps"] += 1
                    elif elapsed > MAX_NON_GAP_DT_SECONDS:
                        counters["over_limit_time_gaps"] += 1
                    else:
                        counters["time_intervals_integrated"] += 1
                        trap_numsec += (prev_current + current) * elapsed / 2
                        right_numsec += current * elapsed
                prev_t, prev_current = when, current
    if counters["numeric_timestamp_rows"] == 0:
        raise ValueError("no valid numeric electrical rows")
    return {
        "source_member":name, "original_column_names":header, "counts":dict(counters),
        "first_valid_timestamp":first.isoformat(timespec="microseconds"),
        "last_valid_timestamp":last.isoformat(timespec="microseconds"),
        "device_labels":sorted(devices),
        "observed_voltage_numeric_min_max":[vmin,vmax],
        "observed_current_numeric_min_max":[imin,imax],
        "bounded_signed_current_numeric_times_seconds_trapezoid":round(trap_numsec,7),
        "bounded_signed_current_numeric_times_seconds_right_endpoint":round(right_numsec,7),
        "excluded_gap_above_seconds":MAX_NON_GAP_DT_SECONDS,
        "current_header_has_no_declared_unit":True,
        "not_absolute_Ah_capacity":True,
        "not_a_discharge_cycle_integral":True
    }


def probe_sp_header(z: zipfile.ZipFile, name: str) -> dict:
    with z.open(name) as f:
        raw = f.read(32768)
    text = raw.decode("utf-8-sig", errors="replace")
    sample = [s.strip()[:220] for s in text.splitlines()[:100] if s.strip()]
    matches = [s for s in sample if re.search(r"Test\s*:|Specimen\s*:|Time|Zeit|Channel|Signal|Unit|Force|Thickness|Weg|Kraft|Start", s, re.IGNORECASE)]
    return {"source_member":name,"sample_bytes":len(raw),"first_100_line_metadata_matches":matches[:16],
            "time_and_force_field_units_verified":False,
            "physical_specimen_identifier_automatically_verified":False}


def inspect_original() -> dict:
    meta_raw = core.get_bytes(core.API, 2_000_000)
    manifest = core.validate_manifest(json.loads(meta_raw))
    blob = core.get_bytes(manifest["download_url"], core.MAX_ZIP_BYTES)
    if len(blob) != manifest["size"] or hashlib.md5(blob).hexdigest() != core.PUBLISHER_MD5:
        raise ValueError("source ZIP failed publisher byte-length/MD5 checks")
    structural = core.audit_archive(blob)
    counts = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        groups = filename_groups(z.infolist())
        for cell in core.PUBLISHER_CELLS:
            g = groups[cell]
            log = scan_electrical_log(z,g["cycling_log"][0])
            if log["counts"].get("numeric_timestamp_rows",0) < 100:
                raise ValueError("unexpectedly short original numeric cycling log " + cell)
            counts[cell] = {
                "publisher_preload_kN":core.PUBLISHER_CELLS[cell],
                "source_folder_identity_only":True,
                "electric_log":log,
                "sp_logs":[probe_sp_header(z,x) for x in g["sp_txt"]],
            }
    return {
        "goal_key":GOAL_KEY, "publisher_doi":core.DOI,
        "distinct_older_graz_four_cell_doi":"10.5281/zenodo.18315429",
        "source_original_md5_verified":core.PUBLISHER_MD5,
        "source_original_sha256":hashlib.sha256(blob).hexdigest(),
        "all_source_zip_crc_verified":structural["zip_crc_all_members_pass"],
        "electric_original_log_count":len(counts),
        "sp_original_log_count":sum(len(x["sp_logs"]) for x in counts.values()),
        "cells":counts,
        "raw_numeric_log_rows_parsed":sum(x["electric_log"]["counts"]["numeric_timestamp_rows"] for x in counts.values()),
        "all_five_cell_folders_have_1_cycling_and_3_sp_logs":True,
        "time_series_signal_alignment_verified":False,
        "sp_physical_force_units_verified":False,
        "electrical_current_units_independently_verified":False,
        "calibrated_capacity_or_soh_recomputed":False,
        "dynamic_impact_measured":False,
        "preload_causal_effect_established":False,
        "old_four_cell_archive_samples_join_verified":False
    }


def main() -> None:
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("output",type=pathlib.Path)
    args=ap.parse_args()
    data=inspect_original()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    for cell,x in data["cells"].items():
        y=x["electric_log"]
        print("REAL_GRAZ_CELL_NUMERIC_PROBE",cell,
              y["counts"],y["first_valid_timestamp"],y["last_valid_timestamp"],
              y["observed_current_numeric_min_max"],flush=True)
        for sp in x["sp_logs"]:
            print("SP_SOURCE_FIELD_METADATA",cell,sp["source_member"],
                  sp["first_100_line_metadata_matches"][:5],flush=True)
    print("NO_PHYSICAL_CALIBRATION_OR_CAPACITY_CLAIM",flush=True)


if __name__=="__main__":
    main()
