"""Publisher-pinned, within-cell original ET/AT capacity from 3 real Figshare ZIPs.

Implements original author feature_extraction.py method: step 21 positive current
(charge), step 22 negative current (discharge), dt*I/3600 integration.
No voltage similarity -> physical copy inference, no field error rate claim.
Original source data may be saved locally in explicit archive directory, but
ONLY anonymized aggregates are emitted in the JSON report.
"""
from __future__ import annotations
from collections import Counter
import csv
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
from zipfile import ZipFile

from research.battery_curve_audit.figshare_three_archive_probe import (
    URL, MAX_META_BYTES, MAX_SOURCE_BYTES, fetch_bounded, inspect_zip,
    validate_source_meta,
)
from research.battery_curve_audit.figshare_three_curve_probe import parse_source_runtime
from research.battery_curve_audit.figshare_identity_provenance import (
    summarize_meta_sidecar, _identity,
)

SOURCE_DOI = "10.6084/m9.figshare.25975315"
AUTHOR_METHOD_REPO = "fst2112/Multi-Stage-Lithium-Ion-Battery-Aging-Dataset-Analysis"
AUTHOR_METHOD_PATH = "src/feature_extraction.py"
AUTHOR_METHOD_SHA = "e6d699223a1df79bf10869f608951c32a0e66c15"
MAX_CSV_MEMBER_BYTES = 60_000_000
MAX_CSV_ROWS = 800_000
MAX_INTERVAL_GAP_S = 120.0
MIN_PHASE_POINTS = 50
MIN_CAPACITY_AH = 0.2
MAX_CAPACITY_AH = 8.0
REQUIRED_HEADER = {"run_time","c_vol","c_cur","step_type"}


def _meta_record(z: ZipFile, name: str) -> dict:
    paired = name[:-4] + "_meta.txt"
    if paired not in z.namelist() or z.getinfo(paired).file_size > 50000:
        raise ValueError("SOURCE_REVIEW_REQUIRED: missing or oversized paired measurement sidecar")
    raw=z.read(paired)
    m=summarize_meta_sidecar(raw)
    fields=m["parsed_fields"]
    if not fields.get("laboratory_identifier") or not fields.get("internal_cell_serial"):
        raise ValueError("SOURCE_REVIEW_REQUIRED: missing original lab/internal serial labels")
    return {
        "paired_meta_sha256": sha256(raw).hexdigest(),
        "lab": _identity(fields["laboratory_identifier"]),
        "serial": _identity(fields["internal_cell_serial"]),
        "temperature": fields.get("climate_chamber_temperature_setpoint"),
        "sidecar_label_names": m["field_keys"],
    }


def inspect_phase(csv_file: ZipFile, name: str) -> dict:
    """Bounded all-row integration, independent monotonic source time."""
    info=csv_file.getinfo(name)
    if info.file_size > MAX_CSV_MEMBER_BYTES:
        raise ValueError("SOURCE_REVIEW_REQUIRED: oversized measurement CSV")
    segments={21:[],22:[]}
    active=None
    count=0
    previous_time=None
    bad_time=0
    distinct_codes=set()
    first_current={21:None,22:None}
    with csv_file.open(name) as source:
        reader=csv.DictReader(io.TextIOWrapper(source,encoding="utf-8-sig",newline=""))
        if not reader.fieldnames or not REQUIRED_HEADER.issubset(reader.fieldnames):
            raise ValueError("SOURCE_REVIEW_REQUIRED: unsupported source measurement columns")
        for row in reader:
            count+=1
            if count>MAX_CSV_ROWS or None in row:
                raise ValueError("SOURCE_REVIEW_REQUIRED: too many or malformed source rows")
            try:
                t=float(parse_source_runtime(row["run_time"]))
                current=float(row["c_cur"])
                voltage=float(row["c_vol"])
                step=int(row["step_type"])
            except (ValueError,TypeError,OverflowError) as exc:
                raise ValueError("SOURCE_REVIEW_REQUIRED: invalid original measurement") from exc
            if not all(__import__("math").isfinite(x) for x in (t,current,voltage)):
                raise ValueError("SOURCE_REVIEW_REQUIRED: nonfinite source measurement")
            if previous_time is not None and t < previous_time:
                raise ValueError("SOURCE_REVIEW_REQUIRED: original clock not monotonic")
            if previous_time is not None and t==previous_time:
                bad_time+=1
            previous_time=t
            distinct_codes.add(step)
            phase=step if (step==21 and current>0 or step==22 and current<0) else None
            if phase != active:
                if phase is not None:
                    segments[phase].append({
                        "points":0,"prev_time":None,"charge_As":0.0,
                        "max_gap_seconds":0.0,"zero_dt_rows":0,
                        "start_v":voltage,"end_v":voltage,
                    })
                active=phase
            if phase is not None:
                seg=segments[phase][-1]
                seg["points"]+=1
                seg["end_v"]=voltage
                if seg["prev_time"] is not None:
                    dt=t-seg["prev_time"]
                    seg["max_gap_seconds"]=max(dt,seg["max_gap_seconds"])
                    if dt==0:
                        seg["zero_dt_rows"]+=1
                    else:
                        # Matches author's step-filtered right-endpoint numerical integration.
                        seg["charge_As"] += dt*abs(current)
                seg["prev_time"]=t
    phase_data={}
    for step in (21,22):
        all_segs=segments[step]
        if len(all_segs)!=1:
            phase_data[str(step)]={"status":"MISSING_OR_MULTIPLE_CAPACITY_SEGMENTS",
                                   "segment_count":len(all_segs),"capacity_Ah":None}
            continue
        seg=all_segs[0]
        q=seg["charge_As"]/3600
        valid=(seg["points"]>=MIN_PHASE_POINTS and seg["max_gap_seconds"]<=MAX_INTERVAL_GAP_S
               and MIN_CAPACITY_AH<=q<=MAX_CAPACITY_AH)
        phase_data[str(step)]={
            "status":"VALID" if valid else "CAPACITY_SEGMENT_REVIEW_REQUIRED",
            "segment_count":1,"rows":seg["points"],
            "zero_duration_rows":seg["zero_dt_rows"],
            "max_gap_seconds":round(seg["max_gap_seconds"],3),
            "capacity_Ah":round(q,6) if valid else None,
            "first_voltage_V":round(seg["start_v"],4),
            "last_voltage_V":round(seg["end_v"],4),
        }
    ready=all(phase_data[str(x)]["status"]=="VALID" for x in (21,22))
    q_mean=round((phase_data["21"]["capacity_Ah"]+phase_data["22"]["capacity_Ah"])/2,6) if ready else None
    return {
        "original_measurement_name":PurePosixPath(name).name,
        "source_rows_processed":count,
        "distinct_step_types":len(distinct_codes),
        "repeated_elapsed_time_rows":bad_time,
        "step21_charging":phase_data["21"],
        "step22_discharging":phase_data["22"],
        "capacity_mean_Ah":q_mean,
        "source_capacity_extractable":ready,
        "source_method":"author_step21_step22_right_endpoint_current_time_integral",
    }


def select_et_at(z: ZipFile, stem: str) -> dict:
    """Require one complete ET and AT record at T23 from the same archive."""
    if not re.fullmatch(r"TP_k01_0[456]",stem):
        raise ValueError("SOURCE_REVIEW_REQUIRED: original calendar archive ID")
    files={}
    for n in z.namelist():
        base=PurePosixPath(n).name
        m=re.fullmatch(re.escape(stem)+r"_(\d{2})_(ET|AT)_T23\.csv",base)
        if m:
            typ=m.group(2)
            files.setdefault(typ,[]).append(n)
    # Distinct source archives may include additional valid RPTs; do not silently
    # choose a convenient AT. Require one per class for defensible comparisons.
    if any(len(files.get(t,[]))!=1 for t in ("ET","AT")):
        return {"decision":"ET_AT_T23_UNIQUE_PAIR_NOT_ESTABLISHED",
                "et_matches":len(files.get("ET",[])),
                "at_matches":len(files.get("AT",[])),
                "et_at_capacity_change_percent":None,
                "capacity_established":False}
    et_name=files["ET"][0]
    at_name=files["AT"][0]
    m0=_meta_record(z,et_name); m1=_meta_record(z,at_name)
    # Original stage+serial and laboratory identity must persist within this
    # publisher archive; equipment/test channel can legitimately change.
    if m0["lab"]!=m1["lab"] or m0["serial"]!=m1["serial"]:
        raise ValueError("SOURCE_REVIEW_REQUIRED: original ET/AT lab or cell serial mismatch")
    et=inspect_phase(z,et_name)
    at=inspect_phase(z,at_name)
    capable=(et["source_capacity_extractable"] and at["source_capacity_extractable"])
    rel=round(100*(at["capacity_mean_Ah"]/et["capacity_mean_Ah"]-1),4) if capable else None
    return {
        "decision":"WITHIN_SOURCE_ET_AT_CAPACITY_RESEARCH_ONLY" if capable else
                   "ORIGINAL_ET_AT_CAPACITY_REVIEW_REQUIRED",
        "et_matches":1,"at_matches":1,
        "publisher_sidecar_lab_internal_serial_match":True,
        "sidecar_et_sha256":m0["paired_meta_sha256"],
        "sidecar_at_sha256":m1["paired_meta_sha256"],
        "et_temperature_source_label":m0["temperature"],
        "at_temperature_source_label":m1["temperature"],
        "et":et,"at":at,
        "et_at_capacity_change_percent":rel,
        "capacity_established":capable,
        "physical_cell_identity_independently_authenticated":False,
        "aging_storage_only_causal_attribution_established":False,
        "reason":"AT follows other-temperature RPTs; observed total ET-to-AT change is not storage-only capacity loss",
    }


def run(original_archive_dir: Path|None=None) -> dict:
    meta_raw=fetch_bounded(URL,MAX_META_BYTES)
    meta=json.loads(meta_raw)
    pins=validate_source_meta(meta)
    if original_archive_dir is not None:
        if not original_archive_dir.is_dir() or list(original_archive_dir.iterdir()):
            raise ValueError("SOURCE_REVIEW_REQUIRED: original archive dir must be empty")
    records=[]
    for pub in pins:
        raw=fetch_bounded("https://ndownloader.figshare.com/files/"+str(pub["id"]),MAX_SOURCE_BYTES)
        digest=inspect_zip(raw,pub)
        stem=pub["name"][:-4]
        with ZipFile(io.BytesIO(raw)) as z:
            pair=select_et_at(z,stem)
        records.append({
            "publisher_archive_id":pub["id"],"publisher_filename":pub["name"],
            "publisher_md5_verified":True,"original_zip_sha256":digest["original_zip_sha256"],
            "original_zip_bytes":len(raw),"original_zip_crc_verified":True,**pair,
        })
        # Optional original licensed source preservation on an ephemeral CI runner,
        # only after exact live publisher MD5 and full member CRC checks.
        if original_archive_dir is not None:
            (original_archive_dir/pub["name"]).write_bytes(raw)
    return {
        "schema":"cano.battery.figshare279.original-k01-three-within-cell-et-at-capacity.v1",
        "publisher_article_id":25975315,
        "publisher_doi":SOURCE_DOI,"source_license":"CC BY 4.0",
        "method":AUTHOR_METHOD_PATH,"original_author_code_blob_sha":AUTHOR_METHOD_SHA,
        "archive_count":len(records),"cells":records,
        "real_original_source_bytes_downloaded":sum(x["original_zip_bytes"] for x in records),
        "source_cell_pair_capacity_calculated":sum(x["capacity_established"] for x in records),
        "physical_cells_independently_authenticated":0,
        "field_FPR_FNR_established":False,
        "production_release_allowed":False,
        "decision":"BOUNDED_WITHIN_CELL_ET_AT_RESEARCH_ONLY",
        "source_note":"Original ET/AT RPT test types 21/22; not a field model sensitivity or calibration claim",
    }


def main(argv=None) -> int:
    args=list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) not in (1,3) or (len(args)==3 and args[1]!="--archive-dir"):
            raise ValueError("usage: et_at_capacity OUTPUT.json [--archive-dir EMPTY_DIR]")
        dest=Path(args[0])
        if dest.exists() or not dest.parent.is_dir():
            raise ValueError("SOURCE_REVIEW_REQUIRED: output exists or parent absent")
        archive_dir=Path(args[2]) if len(args)==3 else None
        report=run(archive_dir)
        with dest.open("x",encoding="utf-8") as fh:
            json.dump(report,fh,indent=2,sort_keys=True)
            fh.write("\n")
        print(json.dumps({
            "decision":report["decision"],
            "source_cell_pair_capacity_calculated":report["source_cell_pair_capacity_calculated"],
            "per_source":[
                {"archive_id":r["publisher_archive_id"],
                 "status":r["decision"],
                 "et_Ah":r.get("et",{}).get("capacity_mean_Ah"),
                 "at_Ah":r.get("at",{}).get("capacity_mean_Ah"),
                 "et_at_pct":r["et_at_capacity_change_percent"]}
                for r in report["cells"]]},sort_keys=True))
        return 0
    except (ValueError,TypeError,KeyError,OSError,csv.Error) as exc:
        print("SOURCE_REVIEW_REQUIRED:",str(exc)[:180],file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
