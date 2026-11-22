"""Original Bayreuth F0001/F0002 machine Ah-Step vs independent current-time integration.

Source: Röder et al., Zenodo 15755725 (CC BY 4.0), DOI 10.5281/zenodo.15755725.
Native instrument values and independently computed charge throughputs are compared
ONLY within the same test program line/segment. No external calibration, fault,
causal aging mechanism, or field validation may be inferred.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

RECORD_ID = "15755725"
RECORD_DOI = "10.5281/zenodo.15755725"
SOURCE_FILES = {
    "F0001": {"size": 16057058, "md5": "8181a89aee2e525ca52b60491ee3209b"},
    "F0002": {"size": 21349140, "md5": "3eaca9d8eff8ccf2d1caf55575a3af76"},
}
REQUIRED_COLUMNS = ["Time[h]", "t-Step[h]", "Line", "Command", "U[V]", "I[A]", "Ah-Step", "Cyc-Count"]
MAX_MEMBER_UNCOMPRESSED = 110_000_000
MAX_TOTAL_UNCOMPRESSED = 260_000_000


def fetch_publisher(cell: str) -> bytes:
    if cell not in SOURCE_FILES:
        raise ValueError("unrecognized source cell")
    url = f"https://zenodo.org/api/records/{RECORD_ID}/files/{cell}.zip/content"
    req = urllib.request.Request(url, headers={"User-Agent": "CANO-independent-reproducibility-audit/1.0"})
    spec = SOURCE_FILES[cell]
    chunks, count = [], 0
    with urllib.request.urlopen(req, timeout=75) as fp:
        while True:
            chunk = fp.read(1 << 20)
            if not chunk:
                break
            count += len(chunk)
            if count > spec["size"]:
                raise ValueError("publisher source exceeds pinned byte size")
            chunks.append(chunk)
    data = b"".join(chunks)
    validate_zip(data, cell)
    return data


def validate_zip(data: bytes, cell: str) -> None:
    spec = SOURCE_FILES[cell]
    if len(data) != spec["size"]:
        raise ValueError(f"{cell} original byte-count mismatch")
    if hashlib.md5(data).hexdigest() != spec["md5"]:
        raise ValueError(f"{cell} original publisher MD5 mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as arc:
        members = arc.infolist()
        if not members or len(members) > 30:
            raise ValueError("source member count out of bounds")
        if sum(x.file_size for x in members) > MAX_TOTAL_UNCOMPRESSED:
            raise ValueError("unexpected source uncompressed size")
        for item in members:
            path = PurePosixPath(item.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("original ZIP path traversal")
            if item.file_size > MAX_MEMBER_UNCOMPRESSED:
                raise ValueError("unreasonably large original member")
        invalid = arc.testzip()
        if invalid:
            raise ValueError(f"ZIP CRC failure: {invalid}")
        names = [x.filename.lower() for x in members]
        for stage in ("m0001_checkup.txt", "m0003_checkup.txt"):
            if sum(stage in n for n in names) != 1:
                raise ValueError(f"missing or duplicate {stage}")


def native_rows(arc: zipfile.ZipFile, member: str):
    """Stream original BaSyTec TXT row by row, never infer columns from positions."""
    with arc.open(member) as fp:
        reader = csv.reader(io.TextIOWrapper(fp, encoding="latin-1", errors="replace", newline=""))
        col = None
        for line in reader:
            if not line:
                continue
            if col is None:
                if line[0].lstrip("~").strip() == "Time[h]":
                    hdr = [v.lstrip("~").strip() for v in line]
                    if not all(v in hdr for v in REQUIRED_COLUMNS):
                        raise ValueError("missing required native data columns")
                    col = {c: hdr.index(c) for c in REQUIRED_COLUMNS}
                continue
            if len(line) <= max(col.values()):
                continue
            try:
                time_h = float(line[col["Time[h]"]]); step_h = float(line[col["t-Step[h]"]])
                vol = float(line[col["U[V]"]]); cur = float(line[col["I[A]"]]); step_ah = float(line[col["Ah-Step"]])
                line_id = line[col["Line"]].strip(); cycle = line[col["Cyc-Count"]].strip()
                command = line[col["Command"]].strip().lower()
                if not all(map(math.isfinite, (time_h, step_h, vol, cur, step_ah))):
                    continue
                if time_h < 0 or step_h < 0 or abs(cur) > 20 or not (0 <= vol <= 6):
                    continue
            except (IndexError, ValueError):
                continue
            yield {"time_h": time_h, "step_h": step_h, "v": vol, "i": cur,
                   "ah": step_ah, "line": line_id, "cycle": cycle, "cmd": command}
        if col is None:
            raise ValueError("native header missing")


def close_segment(seg: dict) -> dict:
    """No extrapolation before the first observation or after the last."""
    records = seg["rows"]
    first = records[0]; last = records[-1]
    sign = -1 if first["cmd"] == "discharge" else 1
    actual_max = max(records, key=lambda x: abs(x["ah"]))
    return {
        "command": first["cmd"], "plan_line": first["line"],
        "cycle_source_label": first["cycle"], "row_count": len(records),
        "time_h_span": last["time_h"] - first["time_h"],
        "source_peak_Ah_Step_abs_Ah": abs(actual_max["ah"]),
        "source_first_Ah_Step_Ah": first["ah"],
        "source_final_Ah_Step_Ah": last["ah"],
        "source_increment_Ah": sign * (last["ah"] - first["ah"]),
        "integral_right_Ah": seg["right_ah"],
        "integral_trapezoid_Ah": seg["trapezoid_ah"],
        "integral_right_minus_source_increment_mAh": 1000*(seg["right_ah"] - sign*(last["ah"]-first["ah"])),
        "integral_trapezoid_minus_source_increment_mAh": 1000*(seg["trapezoid_ah"] - sign*(last["ah"]-first["ah"])),
        "last_measured_voltage_V": last["v"],
        "start_measured_voltage_V": first["v"],
        "start_current_A": first["i"],
        "last_current_A": last["i"],
        "integration_from_observed_first_to_last_only": True,
        "not_calibrated_total_capacity": True,
    }


def scan_checkup(arc: zipfile.ZipFile, member: str) -> dict:
    current = None; total_rows = 0; segments = []; resets = 0
    for x in native_rows(arc, member):
        total_rows += 1
        if x["cmd"] not in ("discharge", "charge"):
            if current is not None:
                segments.append(close_segment(current)); current = None
            continue
        new_segment = (current is None or x["cmd"] != current["rows"][-1]["cmd"] or
                       x["line"] != current["rows"][-1]["line"] or
                       x["cycle"] != current["rows"][-1]["cycle"] or
                       x["time_h"] <= current["rows"][-1]["time_h"] or
                       x["step_h"] < current["rows"][-1]["step_h"] - 1e-8)
        if new_segment:
            if current is not None:
                segments.append(close_segment(current)); resets += 1
            current = {"rows": [x], "right_ah": 0., "trapezoid_ah": 0.}
        else:
            prev = current["rows"][-1]
            dt = x["time_h"] - prev["time_h"]
            sign = -1 if x["cmd"] == "discharge" else 1
            current["right_ah"] += sign * x["i"] * dt
            current["trapezoid_ah"] += sign * (x["i"] + prev["i"]) / 2 * dt
            current["rows"].append(x)
    if current is not None:
        segments.append(close_segment(current))
    # Genuine source authors vary .pln protocol line numbers between source
    # cells: never require F0002 to use F0001's Line 17/15. Inventory actual
    # source line identifiers and pair by same line AND terminal voltage.
    by_type = {"discharge": {}, "charge": {}}
    for item in segments:
        if item["row_count"] < 3 or item["source_peak_Ah_Step_abs_Ah"] <= 0:
            continue
        which = by_type[item["command"]]
        line_id = item["plan_line"]
        if line_id not in which or item["source_peak_Ah_Step_abs_Ah"] > which[line_id]["source_peak_Ah_Step_abs_Ah"]:
            which[line_id] = item
    candidates = {kind: sorted(vals.values(), key=lambda q:-q["source_peak_Ah_Step_abs_Ah"])[:30]
                  for kind, vals in by_type.items()}
    selected = {}
    for typ, line in [("discharge", "17"), ("charge", "15")]:
        if line in by_type[typ]:
            selected[typ] = by_type[typ][line]
    return {"original_member": member, "rows_parsed": total_rows,
            "segments_scanned_charge_or_discharge": len(segments), "restarts_detected": resets,
            "all_plan_lines_with_selected_candidate_count": {k: len(v) for k,v in by_type.items()},
            "candidate_summary_by_command": candidates,
            "selected_step_profiles": selected,
            "analysis_only_source_not_reused_from_Stroebl": True}


def infer_stage_line_offset(bol: dict, eol: dict) -> dict:
    """Infer *observed* plan-line offset from multiple matched source steps.

    Never assume that a particular numeric line retains the same meaning
    between different original checkups. An offset is accepted only when a
    CONSISTENT group contains at least two charge and two discharge pairs.
    Each pair additionally matches instrument voltage endpoints, step duration
    and source throughput, so this is test-data homology, not a verified .pln.
    """
    groups = {}
    for command in ("charge", "discharge"):
        for a in bol["candidate_summary_by_command"][command]:
            for b in eol["candidate_summary_by_command"][command]:
                if min(a["row_count"],b["row_count"]) < 3:
                    continue
                x,y=a["source_peak_Ah_Step_abs_Ah"],b["source_peak_Ah_Step_abs_Ah"]
                if not (0.03 <= min(x,y) and max(x,y)/min(x,y) < 1.25):
                    continue
                if abs(a["last_measured_voltage_V"]-b["last_measured_voltage_V"]) > .02:
                    continue
                if abs(a["start_measured_voltage_V"]-b["start_measured_voltage_V"]) > .25:
                    continue
                t1,t2=a["time_h_span"],b["time_h_span"]
                if min(t1,t2)<=0 or max(t1,t2)/min(t1,t2)>1.20:
                    continue
                try:
                    off=int(a["plan_line"])-int(b["plan_line"])
                except ValueError:
                    continue
                groups.setdefault(off,{"charge":[],"discharge":[]})[command].append((a,b))
    valid=[]
    for offset,pairs in groups.items():
        unique=[]; seen_a=set(); seen_b=set()
        # Disallow multiple matches with the same line. Deterministic highest
        # shared observed Ah throughput is used only within a fixed offset.
        flat=[(cmd,a,b) for cmd in ("charge","discharge") for a,b in pairs[cmd]]
        flat.sort(key=lambda v:-min(v[1]["source_peak_Ah_Step_abs_Ah"],v[2]["source_peak_Ah_Step_abs_Ah"]))
        for cmd,a,b in flat:
            keya=(cmd,a["plan_line"]);keyb=(cmd,b["plan_line"])
            if keya in seen_a or keyb in seen_b:
                continue
            seen_a.add(keya);seen_b.add(keyb);unique.append((cmd,a,b))
        counts={cmd:sum(1 for x in unique if x[0]==cmd) for cmd in ("charge","discharge")}
        if counts["charge"]>=2 and counts["discharge"]>=2:
            valid.append((len(unique),-abs(offset),offset,unique,counts))
    if not valid:
        return {"offset_inferred":False,"reason":"insufficient multi-step charge/discharge waveform agreement; do not assign homologous control steps"}
    _,_,offset,matched,counts=max(valid,key=lambda z:(z[0],z[1]))
    return {"offset_inferred":True,"beginning_minus_ending_plan_line_offset":offset,
            "matched_charge_line_pairs":counts["charge"],"matched_discharge_line_pairs":counts["discharge"],
            "matched_source_control_steps":[{"command":cmd,"beginning_line":a["plan_line"],"ending_line":b["plan_line"],
              "beginning_ah":a["source_peak_Ah_Step_abs_Ah"],"ending_ah":b["source_peak_Ah_Step_abs_Ah"],
              "beginning_duration_h":a["time_h_span"],"ending_duration_h":b["time_h_span"],
              "ending_voltage_difference_V":b["last_measured_voltage_V"]-a["last_measured_voltage_V"]}
              for cmd,a,b in matched],
            "source_testplan_project_file_was_not_available":True,
            "not_author_verified_protocol_equivalence":True}


def select_matched_source_step(bol: dict, eol: dict, command: str, offset: int):
    """Choose the source-derived homologous short-duration checkup step."""
    left={x["plan_line"]:x for x in bol["candidate_summary_by_command"][command]}
    right={x["plan_line"]:x for x in eol["candidate_summary_by_command"][command]}
    possible=[]
    for la,a in left.items():
        for lb,b in right.items():
            try:
                if int(la)-int(lb)!=offset:
                    continue
            except ValueError:
                continue
            if min(a["row_count"],b["row_count"])<3:
                continue
            if min(a["source_peak_Ah_Step_abs_Ah"],b["source_peak_Ah_Step_abs_Ah"])<.03:
                continue
            if abs(a["last_measured_voltage_V"]-b["last_measured_voltage_V"])>.02:
                continue
            if abs(a["start_measured_voltage_V"]-b["start_measured_voltage_V"])>.25:
                continue
            if max(a["time_h_span"],b["time_h_span"])/max(.00001,min(a["time_h_span"],b["time_h_span"]))>1.20:
                continue
            if command=="discharge" and not (2.4<=a["last_measured_voltage_V"]<=3.5):
                continue
            if command=="charge" and not (3.8<=a["last_measured_voltage_V"]<=4.35):
                continue
            possible.append((a,b))
    if not possible:
        return None
    # Prefer a short (~2-hour) checkup rather than ~19-hour slow pulse test.
    short=[(a,b) for a,b in possible if max(a["time_h_span"],b["time_h_span"])<5]
    return max(short or possible,key=lambda p:min(p[0]["source_peak_Ah_Step_abs_Ah"],p[1]["source_peak_Ah_Step_abs_Ah"]))


def analyze(originals: dict[str, bytes]) -> dict:
    data = {}
    for cell in SOURCE_FILES:
        source = originals[cell]
        validate_zip(source, cell)
        with zipfile.ZipFile(io.BytesIO(source)) as arc:
            pair = {}
            for label, token in [("beginning", "m0001_checkup.txt"), ("ending", "m0003_checkup.txt")]:
                members = [x.filename for x in arc.infolist() if x.filename.lower().endswith(token)]
                if len(members) != 1:
                    raise ValueError("expected one original checkup: " + token)
                pair[label] = scan_checkup(arc, members[0])
        alignment=infer_stage_line_offset(pair["beginning"],pair["ending"])
        comparisons = {}
        for typ in ("discharge", "charge"):
            found = select_matched_source_step(pair["beginning"],pair["ending"],typ,
                                               alignment["beginning_minus_ending_plan_line_offset"]) if alignment["offset_inferred"] else None
            if found is None:
                comparisons[typ] = {"comparable": False, "reason": "not enough real source matched control steps to infer a safe program-line offset"}
                continue
            a,b = found
            pair["beginning"]["selected_step_profiles"][typ] = a
            pair["ending"]["selected_step_profiles"][typ] = b
            native_delta = b["source_peak_Ah_Step_abs_Ah"] - a["source_peak_Ah_Step_abs_Ah"]
            integrated_delta = b["integral_trapezoid_Ah"] - a["integral_trapezoid_Ah"]
            comparisons[typ] = {
                "comparable_homologous_source_step": True,
                "beginning_plan_line": a["plan_line"],
                "ending_plan_line": b["plan_line"],
                "inferred_beginning_minus_ending_line_offset": alignment["beginning_minus_ending_plan_line_offset"],
                "multi_step_source_homology_not_original_pln_verified": True,
                "source_line_paired_with_own_original_end_voltage": True,
                "original_program_pln_file_unavailable": True,
                "source_step_delta_mAh": 1000*native_delta,
                "source_step_delta_percent": 100*native_delta/a["source_peak_Ah_Step_abs_Ah"],
                "independently_integrated_trapezoid_delta_mAh": 1000*integrated_delta,
                "difference_of_delta_mAh": 1000*(integrated_delta-native_delta),
                "same_cell_not_independent_sample": True,
                "not_a_certified_capacity_loss": True,
            }
        data[cell] = {
            "source_zip_md5": SOURCE_FILES[cell]["md5"],
            "source_zip_size_bytes": SOURCE_FILES[cell]["size"],
            "zip_crc_pass": True,
            "checkup_profiles": pair,
            "paired_measurement": comparisons,
            "stage_line_offset_alignment": alignment,
        }
    return {
        "source_doi": RECORD_DOI,
        "source_license": "CC BY 4.0",
        "distinct_original_source_cells": len(data),
        "cell_ids": list(data),
        "original_total_checkup_numeric_rows": sum(v["rows_parsed"] for d in data.values() for v in d["checkup_profiles"].values()),
        "comparison": data,
        "integration_method": "measured Time[h], I[A]; right rectangle and trapezoid; contiguous same Line+Command+Cyc-Count and nondecreasing t-Step; no extrapolation",
        "not_an_instrument_calibration": True,
        "not_48_cells_processed": True,
        "not_same_cells_as_Stroebl": True,
        "not_population_aging_certification": True,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("output", type=Path)
    args=p.parse_args()
    d = analyze({cell: fetch_publisher(cell) for cell in SOURCE_FILES})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)+"\n",encoding="utf-8")
    for cell in d["cell_ids"]:
        print("BAYREUTH_TWO_SOURCE_CELLS_MD5_CRC_PASS",cell,d["comparison"][cell]["source_zip_size_bytes"])
        for typ,c in d["comparison"][cell]["paired_measurement"].items():
            print("STEP",cell,typ,round(c.get("source_step_delta_mAh",float('nan')),6),round(c.get("independently_integrated_trapezoid_delta_mAh",float('nan')),6))

if __name__ == "__main__":
    main()