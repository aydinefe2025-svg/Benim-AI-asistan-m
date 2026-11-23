"""Independent raw-original Graz audit: identity of the paired electrical event.

Prior analysis PR #836 counted how MANY SP rows had a nearby electrical time
after hypothetical clock shifts, but did not compare WHICH electrical event.
This module corrects that evidence gap. Shifts here are counterfactual (not
actual clock errors), instrument calibration and experiment phases unproven.
"""
from __future__ import annotations
import argparse, bisect, collections, hashlib, io, json, zipfile
from pathlib import Path
from research.battery_curve_audit import graz_source_preflight as official
from research.battery_curve_audit import graz_signal_alignment as parse

GOAL="graz-20261123-original-electrical-event-identity-under-counterfactual-clock-shift"
CELLS=("01","02","03","04","05")
ELECTRIC_EXPECTED={"01":253861,"02":207383,"03":210541,"04":209558,"05":209994}
SP_EXPECTED={"01":46816,"02":46855,"03":46873,"04":46683,"05":46794}
SHIFTS=(-3.0,3.0)
TOL=1.0

def closest_event_indices(
    electrical:list[tuple[float,str,float,float]],
    sp:list[tuple[float,float,float,float]],
    shift_seconds:float,
    tol_seconds:float=TOL
)->tuple[list[int|None],int]:
    """Nearest timestamp, track actual ELECTRICAL row index not just count.

    Keep the same contested-tie rejection as original published code: exact
    equidistant two records with conflicting source fields cannot be selected.
    """
    if shift_seconds not in (-3.0,0.0,3.0) or tol_seconds!=TOL:
        raise ValueError("unsupported shift or tolerance")
    ts=[e[0] for e in electrical]
    if len(ts)<2 or ts!=sorted(ts):
        raise ValueError("unsorted or missing original electrical source times")
    assigned=[]
    conflicting_ties=0
    for r in sp:
        when=r[0]+shift_seconds
        k=bisect.bisect_left(ts,when)
        neigh=sorted(((abs(ts[i]-when),i) for i in (k-1,k) if 0<=i<len(ts)),
                     key=lambda a:(a[0],a[1]))
        if not neigh or neigh[0][0]>tol_seconds:
            assigned.append(None);continue
        if (len(neigh)>1 and abs(neigh[1][0]-neigh[0][0])<1e-6
                and electrical[neigh[1][1]][1:]!=electrical[neigh[0][1]][1:]):
            assigned.append(None);conflicting_ties+=1;continue
        assigned.append(neigh[0][1])
    return assigned,conflicting_ties

def compare_record_identity(electrical,sp,shift_seconds:float)->dict:
    original,ties0=closest_event_indices(electrical,sp,0.0)
    shifted,tiess=closest_event_indices(electrical,sp,shift_seconds)
    present0=sum(v is not None for v in original)
    presents=sum(v is not None for v in shifted)
    unchanged=sum(a is not None and b is not None and a==b
                  for a,b in zip(original,shifted))
    switched=sum(a is not None and b is not None and a!=b
                 for a,b in zip(original,shifted))
    lost=sum(a is not None and b is None for a,b in zip(original,shifted))
    gained=sum(a is None and b is not None for a,b in zip(original,shifted))
    none=sum(a is None and b is None for a,b in zip(original,shifted))
    unique_matched_electrical_original=len({a for a in original if a is not None})
    unique_matched_electrical_shifted=len({b for b in shifted if b is not None})
    # A changed event index must NOT be called an independently measured
    # false match: no physically calibrated source clock ground truth exists.
    if (unchanged+switched+lost)!=present0 or (unchanged+switched+gained)!=presents:
        raise AssertionError("measured row identity accounting failure")
    if unchanged+switched+lost+gained+none!=len(sp):
        raise AssertionError("source SP row accounting failure")
    return {
        "counterfactual_SP_clock_offset_seconds":shift_seconds,
        "original_SP_rows":len(sp),
        "0_offset_matched_SP_rows":present0,
        "shifted_matched_SP_rows":presents,
        "matched_in_both_same_electrical_source_record_index":unchanged,
        "matched_in_both_DIFFERENT_electrical_source_record_index":switched,
        "lost_matched_SP_rows_under_shift":lost,
        "gained_matched_SP_rows_under_shift":gained,
        "unmatched_in_both":none,
        "conflicting_device_ties_zero_shift":ties0,
        "conflicting_device_ties_shift":tiess,
        "distinct_electrical_records_reused_at_zero_shift":unique_matched_electrical_original,
        "distinct_electrical_records_reused_at_shift":unique_matched_electrical_shifted,
        "not_a_measured_real_clock_offset_or_field_false_positive_rate":True,
    }

def verify_publisher_zip(blob:bytes,publisher_size:int):
    src=official.inspect_archive(blob,publisher_size)
    if (src["source_doi"]!=official.DOI
            or src["original_zip_sha256"]!=hashlib.sha256(blob).hexdigest()
            or not src["publisher_zip_md5_verified"] or not src["zip_crc_verified"]):
        raise ValueError("official source failed MD5 SHA256 ZIP CRC")
    return src

def inspect_original(blob:bytes,publisher_size:int)->dict:
    cert=verify_publisher_zip(blob,publisher_size)
    out={};total_e=0;total_sp=0
    summed={str(s):collections.Counter() for s in SHIFTS}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for cell in CELLS:
            members=[m for m in z.infolist()
                     if not m.is_dir() and official.explicit_cell_in_path(m.filename)==cell]
            el=[m for m in members if official.role_for_member(m.filename)=="charge_discharge_log_candidate"]
            sp_files=[m for m in members if official.role_for_member(m.filename)=="thickness_sp_candidate"]
            if len(el)!=1 or len(sp_files)!=3:
                raise ValueError("no authoritative 1 electric+3 SP real source cell file structure")
            electric=parse.log_samples(z,el[0])
            if len(electric)!=ELECTRIC_EXPECTED[cell]:
                raise ValueError("source electrical row count changed")
            total_e+=len(electric)
            recordings=[];cell_sp_total=0
            for f in sorted(sp_files,key=lambda m:m.filename):
                sp,start=parse.sp_samples(z,f)
                cell_sp_total+=len(sp)
                shifts={}
                for shift in SHIFTS:
                    r=compare_record_identity(electric,sp,shift)
                    shifts[str(shift)]=r
                    for k in ("original_SP_rows","0_offset_matched_SP_rows",
                              "shifted_matched_SP_rows",
                              "matched_in_both_same_electrical_source_record_index",
                              "matched_in_both_DIFFERENT_electrical_source_record_index",
                              "lost_matched_SP_rows_under_shift","gained_matched_SP_rows_under_shift",
                              "unmatched_in_both","conflicting_device_ties_zero_shift",
                              "conflicting_device_ties_shift"):
                        summed[str(shift)][k]+=r[k]
                    # Original two late September SP records must stay separate.
                    if cell=="03" and ("09_09_2025" in f.filename or "10_09_2025" in f.filename):
                        if r["0_offset_matched_SP_rows"]!=0 or r["shifted_matched_SP_rows"]!=0:
                            raise ValueError("late cell 03 SP data wrongly assigned to electrical source")
                recordings.append({"source_cell":cell,"original_sp_filename":f.filename,
                                   "original_sample_rows":len(sp),"source_SP_start_epoch":start,
                                   "shifts":shifts})
            if cell_sp_total!=SP_EXPECTED[cell]:
                raise ValueError("SP source row count changed")
            total_sp+=cell_sp_total
            out[cell]={"original_electrical_records":len(electric),
                       "original_SP_source_rows":cell_sp_total,
                       "publisher_nominal_preload_kN":official.CELL_PRELOAD_KN[cell],
                       "SP_files":recordings}
    if total_e!=1091337 or total_sp!=234021:
        raise ValueError("genuine source populations changed")
    if any(summed[str(s)]["0_offset_matched_SP_rows"]!=204673 for s in SHIFTS):
        raise ValueError("merged original source baseline not replicated")
    if summed["3.0"]["shifted_matched_SP_rows"]!=204666 or summed["-3.0"]["shifted_matched_SP_rows"]!=204671:
        raise ValueError("PR 836 shifted sample totals not replicated")
    return {"goal_key":GOAL,"publisher_original_doi":official.DOI,
            "original_zip_sha256":cert["original_zip_sha256"],
            "original_source_md5":official.OFFICIAL_MD5,
            "full_publisher_zip_crc_and_size_pass":True,
            "physical_cell_folders":len(out),
            "original_electrical_records":total_e,
            "original_SP_records":total_sp,
            "nearest_tolerance_seconds":TOL,
            "shifts_counterfactual_not_observed_clock_errors":list(SHIFTS),
            "row_identity_accounting_by_shift":{k:dict(v) for k,v in summed.items()},
            "cells":out,
            "conclusion_limits":{
              "source_synchronized_external_reference_clock_verified":False,
              "same_experiment_controller_step_verified":False,
              "original_current_absolute_amperes_verified":False,
              "physical_sensor_and_force_calibration_verified":False,
              "capacity_or_SOH_recomputed":False,
              "causal_static_preload_effect_or_dynamic_impact_verified":False,
              "field_false_positive_rate_estimated":False,
            }}

def main()->None:
    ap=argparse.ArgumentParser();ap.add_argument("output",type=Path)
    args=ap.parse_args()
    blob,size=official.get_original()
    d=inspect_original(blob,size)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(d,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    for s,v in d["row_identity_accounting_by_shift"].items():
        print("COUNTERFACTUAL_SOURCE_PAIR_IDENTITY",s,v,flush=True)
    print("NOT_A_MEASURED_CLOCK_CALIBRATION_OR_FALSE_POSITIVE_RATE",flush=True)

if __name__=="__main__":
    main()
