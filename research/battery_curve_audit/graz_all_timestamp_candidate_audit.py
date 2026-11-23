"""Original Graz five-cell electrical timestamp duplicate and nearest-join ambiguity audit.

Review of old nearest-source join: checking bisect neighbors (k-1,k) can miss
OTHER same-timestamp electrical records k+1... with different COM devices.
This audit reads publisher original five-cell archive, detects all duplicate
time groups, and rejects competing distinct source channel readings at the
same closest distance rather than arbitrarily choosing one row.
No inference about calibrated clocks, phases, force, current SI units, SOH or impact.
"""
from __future__ import annotations
import argparse
import bisect
import collections
import hashlib
import io
import json
import pathlib
import zipfile

from research.battery_curve_audit import graz_source_preflight as core
from research.battery_curve_audit import graz_signal_alignment as source_reader
from research.battery_curve_audit import graz_source_power_sp_join_quality as previous

GOAL="graz-20261123-original-five-cell-multidevice-duplicate-timestamp-ambiguity"
SHA="5627a1606b8e378de0e4e4ced99222509bcbbcb725d26da6e7a5fad34aa42fc7"
EXPECTED_ELEC={"01":253861,"02":207383,"03":210541,"04":209558,"05":209994}
EXPECTED_SP={"01":46816,"02":46855,"03":46873,"04":46683,"05":46794}
MAX_GAP=1.0
EPS=1e-6

def duplicate_time_summary(el:list[tuple])->dict:
    if len(el)<2:raise ValueError("empty genuine electrical source")
    ts=[r[0] for r in el]
    if ts!=sorted(ts):raise ValueError("electrical source times reversed")
    duplicated_groups=duplicated_rows=conflicting_groups=conflicting_rows=0
    max_multiplicity=0
    signatures_seen=set()
    examples=[]
    i=0
    while i<len(el):
        j=bisect.bisect_right(ts,ts[i],i)
        n=j-i
        if n>1:
            duplicated_groups+=1
            duplicated_rows+=n
            max_multiplicity=max(max_multiplicity,n)
            signatures={(r[1],r[2],r[3],r[4]) for r in el[i:j]}
            if len(signatures)>1:
                conflicting_groups+=1
                conflicting_rows+=n
                if len(examples)<4:
                    examples.append({
                        "unix_source_time":ts[i],"source_line_numbers":[r[5] for r in el[i:min(j,i+6)]],
                        "device_labels":sorted({r[1] for r in el[i:j]}),
                        "distinct_original_observed_value_tuples":len(signatures),
                    })
        i=j
    return {"original_electrical_rows":len(el),
            "duplicate_original_timestamp_groups":duplicated_groups,
            "source_rows_in_duplicate_timestamp_groups":duplicated_rows,
            "time_groups_with_conflicting_device_or_values":conflicting_groups,
            "rows_in_conflicting_timestamp_groups":conflicting_rows,
            "largest_same_timestamp_source_group":max_multiplicity,
            "small_source_row_identity_examples":examples,
            "independently_known_instrument_clock_sync":False}

def nearest_all_candidate_records(el:list[tuple], sp:list[tuple], tolerance:float=MAX_GAP)->list[dict]:
    """All closest raw electrical rows, including both sides and duplicate groups.

    If any DISTINCT (device, voltage, current, power) competing candidate
    occupies same minimum clock distance, the pairing is indeterminate.
    """
    if tolerance!=MAX_GAP or not el:
        raise ValueError("unsupported physical inference or empty source")
    ts=[r[0] for r in el]
    if ts!=sorted(ts):raise ValueError("source log not sorted")
    ans=[]
    for s in sp:
        t=s[0]
        ix=bisect.bisect_left(ts,t)
        adjacent=[j for j in (ix-1,ix) if 0<=j<len(ts)]
        if not adjacent:
            ans.append({"line":None,"status":"out_of_range"});continue
        nearest_distance=min(abs(ts[j]-t) for j in adjacent)
        if nearest_distance>tolerance:
            ans.append({"line":None,"status":"out_of_range"});continue
        close_times={ts[j] for j in adjacent if abs(abs(ts[j]-t)-nearest_distance)<=EPS}
        # The predecessor could be only one row in a much larger SAME-time
        # duplicate group. Expanding with bisect_left/right avoids silent bias.
        groups=[]
        for x in sorted(close_times):
            lo=bisect.bisect_left(ts,x)
            hi=bisect.bisect_right(ts,x)
            groups.extend(el[lo:hi])
        if not groups:
            raise AssertionError("closest source time group unexpectedly empty")
        signatures={(r[1],r[2],r[3],r[4]) for r in groups}
        if len(signatures)>1:
            ans.append({"line":None,"status":"ambiguous_distinct_source_readings",
                        "competing_original_source_rows":len(groups),
                        "competing_source_devices":len({r[1] for r in groups})})
        elif len(groups)>1:
            ans.append({"line":min(r[5] for r in groups),
                        "status":"duplicate_identical_reading_row_id_not_unique",
                        "competing_original_source_rows":len(groups)})
        else:
            ans.append({"line":groups[0][5],"status":"unique_closest_source_row"})
    return ans

def compare_old_to_complete(el:list[tuple],sp:list[tuple])->dict:
    prev=previous.nearest_source_line_ids(el,sp)
    curr=nearest_all_candidate_records(el,sp)
    c=collections.Counter()
    c["original_SP_source_rows"]=len(sp)
    for old,new in zip(prev,curr):
        new_line=new["line"]
        c["original_algorithm_matches"]+=old is not None
        c["complete_algorithm_matches"]+=new_line is not None
        c[new["status"]]+=1
        if old is not None and new_line is None:
            c["previously_accepted_pair_now_rejected"]+=1
        elif old is None and new_line is not None:
            c["previously_rejected_pair_now_accepted"]+=1
        elif old is not None and new_line is not None:
            if old==new_line:c["same_original_electrical_line"]+=1
            else:c["different_original_electrical_line"]+=1
    if c["original_algorithm_matches"]!=(
        c["previously_accepted_pair_now_rejected"]+
        c["same_original_electrical_line"]+
        c["different_original_electrical_line"]
    ):raise AssertionError("old source match partition failed")
    if c["complete_algorithm_matches"]!=(
        c["previously_rejected_pair_now_accepted"]+
        c["same_original_electrical_line"]+
        c["different_original_electrical_line"]
    ):raise AssertionError("new source match partition failed")
    if sum(c[k] for k in (
        "unique_closest_source_row",
        "duplicate_identical_reading_row_id_not_unique",
        "ambiguous_distinct_source_readings","out_of_range"))!=len(sp):
        raise AssertionError("all-original-SP accounting failed")
    return dict(c)

def inspect_archive(blob:bytes,size:int)->dict:
    metadata=core.inspect_archive(blob,size)
    if (metadata["source_doi"]!=core.DOI or metadata["original_zip_sha256"]!=SHA
        or hashlib.sha256(blob).hexdigest()!=SHA
        or not metadata["publisher_zip_md5_verified"] or not metadata["zip_crc_verified"]):
        raise ValueError("source authenticity broken")
    output={}; all_stats=collections.Counter()
    tot_e=tot_sp=0; total_duplicates=total_conflicting=0
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for cell in EXPECTED_ELEC:
            ms=[m for m in z.infolist() if not m.is_dir() and core.explicit_cell_in_path(m.filename)==cell]
            ef=[m for m in ms if core.role_for_member(m.filename)=="charge_discharge_log_candidate"]
            sf=[m for m in ms if core.role_for_member(m.filename)=="thickness_sp_candidate"]
            if len(ef)!=1 or len(sf)!=3:raise ValueError("wrong original cell source provenance")
            el, flagged, devices=previous.original_electrical_rows(z,ef[0])
            if len(el)!=EXPECTED_ELEC[cell]:raise ValueError("original electrical count drift")
            tot_e+=len(el)
            dup=duplicate_time_summary(el)
            total_duplicates+=dup["duplicate_original_timestamp_groups"]
            total_conflicting+=dup["time_groups_with_conflicting_device_or_values"]
            per_sp=[];cell_sp_total=0
            for m in sorted(sf,key=lambda p:p.filename):
                sp,start=source_reader.sp_samples(z,m)
                cell_sp_total+=len(sp)
                stats=compare_old_to_complete(el,sp)
                for k,v in stats.items():all_stats[k]+=v
                stats["original_sp_source_filename"]=m.filename
                stats["original_sp_source_start_epoch"]=start
                per_sp.append(stats)
                if cell=="03" and ("09_09_2025" in m.filename or "10_09_2025" in m.filename):
                    if stats["complete_algorithm_matches"]!=0:raise ValueError("late SP incorrectly paired")
            if cell_sp_total!=EXPECTED_SP[cell]:raise ValueError("source SP sample count drift")
            tot_sp+=cell_sp_total
            output[cell]={"source_preload_kN":core.CELL_PRELOAD_KN[cell],
                          "original_electrical_source_rows":len(el),
                          "original_sensor_rows":cell_sp_total,
                          "original_device_labels":dict(sorted(devices.items())),
                          "same_time_electrical_source_audit":dup,
                          "sp_original_3_files":per_sp}
    if (tot_e,tot_sp)!=(1091337,234021):
        raise ValueError("full source population differs")
    if all_stats["original_algorithm_matches"]!=204673:
        raise ValueError("baseline source 1s join result changed")
    return {"goal_key":GOAL,"source_doi":core.DOI,"original_sha256":SHA,
            "publisher_md5":core.OFFICIAL_MD5,"original_publisher_crc_and_size_verified":True,
            "real_electrical_source_rows":tot_e,"real_sp_source_rows":tot_sp,
            "same_cell_closest_time_tolerance_s":MAX_GAP,
            "original_duplicate_time_groups":total_duplicates,
            "original_conflicting_same_time_groups":total_conflicting,
            "all_cells":output,
            "all_sp_join_counts":dict(all_stats),
            "not_proven":{
              "independently_calibrated_instrument_clocks":True,
              "controller_protocol_phase":True,
              "physical_sensor_force_calibration":True,
              "electrical_current_SI_unit":True,
              "calibrated_capacity_Ah_or_SOH":True,
              "causal_preload_effect_or_impact_safety":True,
              "physical_production_release":True
            },
            "interpretation":"This is a source ambiguity audit. Closest timestamp alone does not prove phase alignment, instrument synchronization, or SI physical validity."}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("output",type=pathlib.Path)
    args=ap.parse_args()
    blob,size=core.get_original()
    d=inspect_archive(blob,size)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(d,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    print("GRAZ_REAL_ORIGINAL_DUPLICATE_TIMESTAMPS",d["original_duplicate_time_groups"],d["original_conflicting_same_time_groups"])
    print("GRAZ_REAL_ORIGINAL_ALL_CANDIDATE_JOIN",d["all_sp_join_counts"])
    for k,v in d["all_cells"].items():
        print("ORIGINAL_CELL_DUPLICATE_AND_SP",k,
              v["same_time_electrical_source_audit"]["duplicate_original_timestamp_groups"],
              sum(x["complete_algorithm_matches"] for x in v["sp_original_3_files"]))
    print("NUMERICAL_ROW_JOIN_NOT_CALIBRATED_INSTRUMENT_CLOCK",flush=True)
if __name__=="__main__":main()
