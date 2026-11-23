"""Start-time SCREEN only: 15 Graz SP files versus 5 electrical log windows.

Compares source-embedded SP Unix start times with instrument filename stamps
and with electrical log first/last recorded datetimes. This does not prove
same-clock sync, all signal rows overlap, or mechanistic/causal relationships.
Graz study DOI 10.5281/zenodo.22079387, not four-cell 18315429.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import re
from zoneinfo import ZoneInfo

ORIGINAL_DOI = "10.5281/zenodo.22079387"
GOAL_KEY = "graz-20261123-electrical-sp-start-screen-five-real-cells"
FILENAME_RE = re.compile(r"(\d{2}_\d{2}_\d{4}_\d{2}_\d{2}_\d{2})_logfile[.]txt$", re.IGNORECASE)
HEADER_RE = re.compile(r"Start\s+time\s*:\s*([0-9]+(?:[.][0-9]+)?)", re.IGNORECASE)
GRAZ_LOCAL_ZONE = ZoneInfo("Europe/Vienna")


def analyze_cell(cell: str, observed: dict) -> list[dict]:
    electrical = observed["electric_log"]
    lo = dt.datetime.fromisoformat(electrical["first_valid_timestamp"])
    hi = dt.datetime.fromisoformat(electrical["last_valid_timestamp"])
    if not lo < hi:
        raise ValueError("invalid electrical original time bounds")
    outputs = []
    for sp in observed["sp_logs"]:
        name = pathlib.PurePosixPath(sp["source_member"]).name
        found = FILENAME_RE.search(name)
        if not found:
            raise ValueError("SP start filename format unknown, cannot join")
        name_local = dt.datetime.strptime(found.group(1), "%d_%m_%Y_%H_%M_%S")
        matches = [HEADER_RE.search(s) for s in sp["first_100_line_metadata_matches"]]
        epochs = [float(m.group(1)) for m in matches if m]
        if len(epochs) != 1:
            raise ValueError("expected one genuine SP Unix start header")
        embedded_local = dt.datetime.fromtimestamp(
            epochs[0], dt.timezone.utc).astimezone(GRAZ_LOCAL_ZONE).replace(tzinfo=None)
        header_vs_filename_seconds = (embedded_local - name_local).total_seconds()
        if abs(header_vs_filename_seconds) > 90:
            raise ValueError("SP Unix start versus instrument filename disagreement")
        within = lo <= embedded_local <= hi
        outputs.append({
            "cell_source_folder": cell, "sp_source_member": sp["source_member"],
            "sp_start_unix_seconds": epochs[0],
            "sp_start_graz_local_assumed": embedded_local.isoformat(timespec="microseconds"),
            "sp_filename_local": name_local.isoformat(),
            "sp_filename_vs_epoch_seconds": round(header_vs_filename_seconds, 4),
            "electrical_first_local_unzoned": lo.isoformat(),
            "electrical_last_local_unzoned": hi.isoformat(),
            "sp_start_within_electric_recording_window_candidate":within,
            "definite_same_cell_mechanical_electric_signal_join":False,
            "start_within_window_not_full_signal_overlap":True,
        })
    return outputs


def analyze_real_probe(d: dict) -> dict:
    if d.get("publisher_doi") != ORIGINAL_DOI or set(d.get("cells",{})) != set(["01","02","03","04","05"]):
        raise ValueError("source identity or original five cell IDs wrong")
    checks = [x for cell in sorted(d["cells"])
              for x in analyze_cell(cell, d["cells"][cell])]
    if len(checks) != 15:
        raise ValueError("not exactly fifteen original SP start records")
    inside = [x for x in checks if x["sp_start_within_electric_recording_window_candidate"]]
    outside = [x for x in checks if not x["sp_start_within_electric_recording_window_candidate"]]
    return {"goal_key":GOAL_KEY, "original_source_doi":ORIGINAL_DOI,
            "underlying_numeric_source_goal_key":d.get("goal_key"),
            "comparison_timezone_assumption":"Europe/Vienna for Unix SP epochs; electrical original timestamps have no embedded UTC zone",
            "start_timestamp_consistency_bound_seconds":90,
            "sp_starts_inside_electrical_window_candidate_count":len(inside),
            "sp_starts_outside_electrical_window_count":len(outside),
            "outside_electrical_window_sp_cells":sorted([x["cell_source_folder"] for x in outside]),
            "sp_starts":checks,
            "unverified_actual_signal_row_time_overlap":True,
            "unverified_interinstrument_clock_synchronization":True,
            "not_a_capacity_mechanical_damage_or_impact_estimate":True}


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("source_probe_json",type=pathlib.Path)
    p.add_argument("output",type=pathlib.Path)
    a=p.parse_args()
    result=analyze_real_probe(json.loads(a.source_probe_json.read_text(encoding="utf-8")))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    print("SP_START_WINDOW_SCREEN",result["sp_starts_inside_electrical_window_candidate_count"],
          result["sp_starts_outside_electrical_window_count"],
          result["outside_electrical_window_sp_cells"],flush=True)


if __name__ == "__main__":
    main()
