"""Audit actual Graz SP↔electrical nearest-record joins after V/I/P discrepancy quarantine.

Genuine 5-cell publisher archive only, full official ZIP MD5/SHA256/CRC.
Source COM4 rows with anomalous numeric Power versus Voltage*Current
were identified independently in merged PR #847. This new study asks if
*those specific rows* contaminate original 204,673 same-cell SP timestamp
pairs, and how removing them changes individual electrical record IDs.

The existing 1s nearest-timestamp metric is *not* a certified device clock
calibration, charge/discharge phase, calibrated Ah, or physical safety.
Raw originals are never rewritten, and anomalous values are not interpreted
as proven physical instrument defects.
"""
from __future__ import annotations
import argparse, bisect, collections, hashlib, io, json, math, pathlib, zipfile
from research.battery_curve_audit import graz_source_preflight as core
from research.battery_curve_audit import graz_source_time_gate as clock
from research.battery_curve_audit import graz_signal_alignment as sp_parse

GOAL="graz-20261123-five-original-COM4-zero-power-SP-join-contamination"
ZIP_SHA="5627a1606b8e378de0e4e4ced99222509bcbbcb725d26da6e7a5fad34aa42fc7"
EXPECTED_ELEC={"01":253861,"02":207383,"03":210541,"04":209558,"05":209994}
EXPECTED_SP={"01":46816,"02":46855,"03":46873,"04":46683,"05":46794}
EXPECTED_QUARANTINED={"01":284,"02":352,"03":308,"04":450,"05":506}
SOURCE_HEADER=("Time","Device","Voltage","Current","Power")
MAX_TOLERANCE_S=1.0


def finite(x:str)->float:
    v=float(x.strip())
    if not math.isfinite(v):
        raise ValueError("nonfinite source measurement")
    return v


def inconsistent_power(v:float,i:float,p:float)->bool:
    """Exact PR #847 >=0.01 V*I and >5% residual numeric screen."""
    if not all(math.isfinite(k) for k in (v,i,p)):
        raise ValueError("nonfinite electrical measure")
    vi=v*i
    return abs(vi)>=.01 and abs(p/vi-1)>0.05


def original_electrical_rows(z:zipfile.ZipFile, member:zipfile.ZipInfo):
    """Source line numbers are stable row identities, not inferred phases."""
    out=[]; bad_lines=set(); devices=collections.Counter()
    with z.open(member) as raw:
        header=raw.readline().decode("utf-8-sig",errors="strict").strip()
        if tuple(x.strip() for x in header.split(","))!=SOURCE_HEADER:
            raise ValueError("unexpected electrical source schema")
        for line_no,raw_line in enumerate(raw,2):
            line=raw_line.decode("utf-8-sig",errors="strict").strip()
            if not line:continue
            parts=[x.strip() for x in line.split(",")]
            if len(parts)!=5:
                raise ValueError("unexpected original electrical row")
            t=clock.parse_log_token(parts[0])
            dev=parts[1]
            if not (dev.startswith("COM") and dev[3:].isdigit()):
                raise ValueError("unverified electrical acquisition device")
            v,i,p=(finite(q) for q in parts[2:])
            if not (0<v<10 and abs(i)<=200 and abs(p)<=2000):
                raise ValueError("out-of-bounds source electrical value")
            flagged=inconsistent_power(v,i,p)
            if flagged:
                # The independently archived original PR #847 shows exactly
                # 1,900 COM4 P=0 source cases. Any new pattern fails closed.
                if not (dev=="COM4" and p==0 and abs(v*i)>=1):
                    raise ValueError("new outlier pattern needs independent review")
                if line_no in bad_lines:
                    raise ValueError("duplicate quarantined source electrical line")
                bad_lines.add(line_no)
            devices[dev]+=1
            out.append((t,dev,v,i,p,line_no,flagged))
            if len(out)>800000:
                raise ValueError("source electrical row cap exceeded")
    if len(out)<100:
        raise ValueError("source electrical log empty")
    if any(out[k][0]>out[k+1][0] for k in range(len(out)-1)):
        raise ValueError("source electrical record clock not monotonic")
    return out,bad_lines,devices


def nearest_source_line_ids(
        rows:list[tuple], sp:list[tuple],tol_seconds:float=MAX_TOLERANCE_S)->list[int|None]:
    if not rows or tol_seconds!=MAX_TOLERANCE_S:
        raise ValueError("invalid source or unregistered tolerance")
    ts=[r[0] for r in rows]
    if any(ts[k]>ts[k+1] for k in range(len(ts)-1)):
        raise ValueError("unsorted electrical source")
    result=[]
    for r in sp:
        t=r[0]
        j=bisect.bisect_left(ts,t)
        neighboring=sorted(
            ((abs(ts[k]-t),k) for k in (j-1,j) if 0<=k<len(rows)),
            key=lambda x:(x[0],x[1]))
        if not neighboring or neighboring[0][0]>tol_seconds:
            result.append(None);continue
        if (len(neighboring)>1 and abs(neighboring[0][0]-neighboring[1][0])<1e-6
            and rows[neighboring[0][1]][1:4]!=rows[neighboring[1][1]][1:4]):
            result.append(None);continue
        result.append(rows[neighboring[0][1]][5])
    return result


def compare_file(electrical:list[tuple],sp:list[tuple],flagged_lines:set[int])->dict:
    before=nearest_source_line_ids(electrical,sp)
    clean=[row for row in electrical if not row[6]]
    if not clean:raise ValueError("no usable original electrical rows remain")
    after=nearest_source_line_ids(clean,sp)
    metrics=collections.Counter()
    for a,b in zip(before,after):
        if a is not None:metrics["before_matched_SP_rows"]+=1
        if b is not None:metrics["after_matched_SP_rows"]+=1
        if a in flagged_lines:metrics["before_mapped_to_quarantined_electrical_power_row"]+=1
        if a is not None and a==b:metrics["same_paired_source_electrical_line_after_quarantine"]+=1
        if a is not None and b is not None and a!=b:metrics["changed_paired_source_electrical_line_after_quarantine"]+=1
        if a is not None and b is None:metrics["lost_SP_match_after_quarantine"]+=1
        if a is None and b is not None:metrics["gained_SP_match_after_quarantine"]+=1
        if a is None and b is None:metrics["unmatched_in_both"]+=1
        if b in flagged_lines:raise AssertionError("quarantined source line was used in clean pairing")
    metrics["original_SP_rows"]=len(sp)
    if metrics["before_matched_SP_rows"]!=(
            metrics["same_paired_source_electrical_line_after_quarantine"]
            + metrics["changed_paired_source_electrical_line_after_quarantine"]
            + metrics["lost_SP_match_after_quarantine"]):
        raise AssertionError("before SP counts do not balance")
    if metrics["after_matched_SP_rows"]!=(
            metrics["same_paired_source_electrical_line_after_quarantine"]
            + metrics["changed_paired_source_electrical_line_after_quarantine"]
            + metrics["gained_SP_match_after_quarantine"]):
        raise AssertionError("after SP counts do not balance")
    if metrics["before_matched_SP_rows"]+metrics["gained_SP_match_after_quarantine"]+metrics["unmatched_in_both"]!=len(sp):
        raise AssertionError("SP source partition does not balance")
    return dict(metrics)


def inspect_original(original_blob:bytes,declared_size:int)->dict:
    meta=core.inspect_archive(original_blob,declared_size)
    if (meta["source_doi"]!="10.5281/zenodo.22079387"
        or meta["original_zip_sha256"]!=ZIP_SHA
        or not meta["publisher_zip_md5_verified"] or not meta["zip_crc_verified"]
        or hashlib.sha256(original_blob).hexdigest()!=ZIP_SHA):
        raise ValueError("official published original ZIP not authenticated")
    per_cell={};total_e=total_sp=total_flag=0
    combined=collections.Counter()
    with zipfile.ZipFile(io.BytesIO(original_blob)) as z:
        for cell in EXPECTED_ELEC:
            owned=[m for m in z.infolist() if not m.is_dir()
                   and core.explicit_cell_in_path(m.filename)==cell]
            electricity=[m for m in owned if core.role_for_member(m.filename)=="charge_discharge_log_candidate"]
            sensors=[m for m in owned if core.role_for_member(m.filename)=="thickness_sp_candidate"]
            if len(electricity)!=1 or len(sensors)!=3:
                raise ValueError("physical source file identity not verified")
            source_rows,flagged,devices=original_electrical_rows(z,electricity[0])
            if len(source_rows)!=EXPECTED_ELEC[cell] or len(flagged)!=EXPECTED_QUARANTINED[cell]:
                raise ValueError("previous independently authenticated electrical/discrepancy count changed")
            sensor_stats=[];nsp=0
            for member in sorted(sensors,key=lambda m:m.filename):
                sp,source_start=sp_parse.sp_samples(z,member)
                nsp+=len(sp)
                metric=compare_file(source_rows,sp,flagged)
                metric.update({"source_member_path":member.filename,"sp_start_epoch":source_start,
                               "scope":"same physical source folder; nearest timestamp, not lab protocol or calibrated phase"})
                for key,value in metric.items():
                    if isinstance(value,int):combined[key]+=value
                sensor_stats.append(metric)
                if cell=="03" and ("09_09_2025" in member.filename or "10_09_2025" in member.filename):
                    if metric.get("before_matched_SP_rows",0) or metric.get("after_matched_SP_rows",0):
                        raise ValueError("post-electrical cell 03 sensor falsely matched")
            if nsp!=EXPECTED_SP[cell]:
                raise ValueError("source SP count drift")
            per_cell[cell]={"original_electrical_rows":len(source_rows),
                            "original_SP_rows":nsp,"publisher_nominal_preload_kN":core.CELL_PRELOAD_KN[cell],
                            "original_numeric_power_quarantine_rows":len(flagged),
                            "source_electrical_device_row_counts":dict(sorted(devices.items())),
                            "original_electrical_member_path":electricity[0].filename,
                            "SP_3_files":sensor_stats}
            total_e+=len(source_rows);total_sp+=nsp;total_flag+=len(flagged)
    if (total_e,total_sp,total_flag)!=(1091337,234021,1900):
        raise ValueError("source source-count discrepancy from prior full audit")
    if combined["before_matched_SP_rows"]!=204673:
        raise ValueError("the previous 5-cell real baseline could not be reproduced")
    return {"goal_key":GOAL,"source_doi":core.DOI,"publisher_pinned_md5":core.OFFICIAL_MD5,
            "publisher_source_original_sha256":ZIP_SHA,"zip_crc_and_declared_size_verified":True,
            "genuine_original_electrical_rows":total_e,
            "genuine_original_sp_sensor_rows":total_sp,
            "original_numeric_P_vs_VI_discrepancy_rows":total_flag,
            "baseline_same_cell_1s_sp_pairs":204673,
            "all_five_cell_original_join_quality":dict(combined),
            "cells":per_cell,
            "hard_scientific_limits":{
               "measured_actual_electrical_controller_stage_identity":False,
               "independently_certified_electrical_current_units":False,
               "source_SP_force_sensor_calibration_verified":False,
               "genuine_physical_dual_instrument_clock_calibrated":False,
               "capacity_or_state_of_health_reconstructed":False,
               "static_preload_causes_capacity_loss_demonstrated":False,
               "dynamic_battery_impact_experiment":False,
               "field_false_positive_rate_estimated":False,
               "physical_production_release_approved":False,
            }}


def main()->None:
    p=argparse.ArgumentParser();p.add_argument("output",type=pathlib.Path)
    args=p.parse_args();blob,size=core.get_original()
    result=inspect_original(blob,size)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    print("GRAZ_SOURCE_5CELL_JOINT_VIP_SP_QUALITY",result["all_five_cell_original_join_quality"])
    for cell,c in result["cells"].items():
        print("ORIGINAL_CELL_VIP_SP",cell,c["original_numeric_power_quarantine_rows"],
              sum(m.get("before_mapped_to_quarantined_electrical_power_row",0)
                  for m in c["SP_3_files"]),flush=True)

if __name__=="__main__":
    main()
