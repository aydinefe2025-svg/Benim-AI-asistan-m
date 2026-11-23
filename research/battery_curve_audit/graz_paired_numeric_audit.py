"""Real same-folder / same-clock mechanical-electrical observations from Graz ZIP.

NOT dynamic impact; NOT calibrated swelling-force or capacity-fade inference.
Positive/negative integral is electrical throughput only, not capacity retention.
Every observation is read directly from the MD5-pinned publisher original ZIP.
"""
from __future__ import annotations
from bisect import bisect_left
from collections import Counter
import csv
from datetime import datetime
import io
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile
from .graz_paired_source_probe import RECORD, FILENAME, MD5, MAX_ZIP, check_metadata, download

PRELOAD_KN={"01":0.0,"02":1.5,"03":3.0,"04":5.0,"05":15.0}
MAX_PAIR_GAP_S=3.0
MAX_ELECTRICAL_INTEGRAL_GAP_S=5.0
SP_RE=re.compile(r"^\d\d/\d\d/\d{4}\s+\d\d:\d\d:\d\d(?:\.\d+)?\s+")

def finite(x):
    v=float(x)
    if not math.isfinite(v):
        raise ValueError("nonfinite measurement")
    return v

def log_rows(handle):
    text=io.TextIOWrapper(handle,encoding="utf-8-sig",errors="replace",newline="")
    reader=csv.reader(text)
    head=next(reader,None)
    if not head or [x.strip() for x in head]!=["Time","Device","Voltage","Current","Power"]:
        raise ValueError("unexpected electrical logger schema")
    last=None;out=[]
    for row in reader:
        if not row or all(not v.strip() for v in row): continue
        if len(row)!=5: raise ValueError("electrical source columns drift")
        t=datetime.strptime(row[0].strip(),"%Y-%m-%d_%H-%M-%S-%f")
        if last is not None and t<=last: raise ValueError("non-monotonic logger timestamp")
        last=t
        v,i,p=(finite(row[j].strip()) for j in (2,3,4))
        out.append((t,v,i,p))
    if len(out)<2: raise ValueError("insufficient electrical time series")
    return out

def sp_rows(handle):
    text=io.TextIOWrapper(handle,encoding="utf-8-sig",errors="replace",newline="")
    lines=iter(text); started=False; last=None;out=[]
    for line in lines:
        if not started:
            if "Sensor 1[micro-m]" in line and "Sensor 2[micro-m]" in line and "Time" in line:
                started=True
            continue
        if not SP_RE.match(line.strip()): continue
        fields=line.split()
        if len(fields)<7:raise ValueError("SP numeric row lost one channel")
        ts=fields[0]+" "+fields[1]
        try: t=datetime.strptime(ts,"%d/%m/%Y %H:%M:%S")
        except ValueError: t=datetime.strptime(ts,"%d/%m/%Y %H:%M:%S.%f")
        if last is not None and t<=last: raise ValueError("SP non-monotonic clock")
        last=t
        nums=[finite(x) for x in fields[2:7]]
        out.append((t,nums[2],nums[3],nums[4]))
    if not started or not out:raise ValueError("no SP schema or observations")
    return out

def integrate_signs(rows):
    positive=negative=0.0; paired=0; gaps=0; maxgap=0.
    for (t0,_,i0,_),(t1,_,i1,_) in zip(rows,rows[1:]):
        dt=(t1-t0).total_seconds()
        if dt<=0: raise ValueError("nonmonotonic time")
        maxgap=max(maxgap,dt)
        if dt>MAX_ELECTRICAL_INTEGRAL_GAP_S:
            gaps+=1
            continue
        # Signed trapezoid areas; if current crosses 0, split to avoid
        # mathematically cancelling opposite direction throughputs.
        if i0*i1<0:
            alpha=abs(i0)/(abs(i0)+abs(i1))
            positive+=max(i0,0)*dt*alpha/2/3600 + max(i1,0)*dt*(1-alpha)/2/3600
            negative+=max(-i0,0)*dt*alpha/2/3600 + max(-i1,0)*dt*(1-alpha)/2/3600
        else:
            average=(i0+i1)/2
            if average>=0:positive+=average*dt/3600
            else:negative-=average*dt/3600
        paired+=1
    return {"positive_current_throughput_Ah":round(positive,7),
            "negative_current_throughput_Ah":round(negative,7),
            "integrated_intervals":paired,"excluded_large_gaps":gaps,
            "max_logger_gap_s":round(maxgap,3)}

def align(log,sp):
    times=[r[0] for r in log]
    matched=[]
    for t,s1,s2,s3 in sp:
        ix=bisect_left(times,t)
        nearest=[]
        if ix<len(log):nearest.append(ix)
        if ix>0:nearest.append(ix-1)
        k=min(nearest,key=lambda j:abs((times[j]-t).total_seconds()))
        distance=abs((times[k]-t).total_seconds())
        if distance<=MAX_PAIR_GAP_S:
            matched.append((t,log[k][2],s1,s2,s3,distance))
    def rng(idx):
        vals=[row[idx] for row in matched]
        return [round(min(vals),6),round(max(vals),6)] if vals else None
    return {"sp_measurements":len(sp),"time_aligned_measurements":len(matched),
            "alignment_fraction":round(len(matched)/len(sp),6),
            "nearest_clock_error_max_s":round(max((x[5] for x in matched),default=0.),6),
            "sensor1_aligned_range_um":rng(2),"sensor2_aligned_range_um":rng(3),
            "sensor3_aligned_range_um":rng(4),
            "positive_current_aligned_points":sum(x[1]>0.01 for x in matched),
            "negative_current_aligned_points":sum(x[1]<-0.01 for x in matched),
            "zero_current_aligned_points":sum(abs(x[1])<=0.01 for x in matched)}

def file_groups(names):
    grouped={k:{"logger":[],"sp":[]} for k in PRELOAD_KN}
    for name in names:
        bits=PurePosixPath(name).parts
        m=[re.fullmatch(r"Fresh cell (0[1-5])",part) for part in bits]
        ids=[x.group(1) for x in m if x]
        if len(ids)!=1:continue
        cell=ids[0]
        if name.lower().endswith(".log"): grouped[cell]["logger"].append(name)
        elif name.lower().endswith(".txt") and PurePosixPath(name).name.startswith("SP_"):
            grouped[cell]["sp"].append(name)
    for cell,g in grouped.items():
        if len(g["logger"])!=1 or len(g["sp"])<1:
            raise ValueError("missing or ambiguous source for physical cell "+cell)
    return grouped

def audit():
    endpoint=f"https://zenodo.org/api/records/{RECORD}"
    meta=json.loads(download(endpoint,2_000_000))
    size=check_metadata(meta)
    raw=download(endpoint+"/files/"+__import__("urllib.parse",fromlist=["quote"]).quote(FILENAME)+"/content",MAX_ZIP)
    if len(raw)!=size or hashlib.md5(raw).hexdigest()!=MD5:
        raise ValueError("publisher ZIP identity mismatch")
    from .graz_paired_source_probe import inventory
    verified_inventory=inventory(raw)  # full member CRC, traversal, bombs
    grouped=file_groups(verified_inventory["names"])
    results=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for cell in sorted(grouped):
            g=grouped[cell]
            with z.open(g["logger"][0]) as f:
                logs=log_rows(f)
            mechanical=[]
            for name in sorted(g["sp"]):
                with z.open(name) as f: mechanical.extend(sp_rows(f))
            # Multiple SP recordings on same day must be chronologically distinct
            mechanical.sort(key=lambda r:r[0])
            if len({x[0] for x in mechanical})!=len(mechanical):
                raise ValueError("duplicated SP clock readings")
            coupling=align(logs,mechanical)
            results.append({
                "physical_cell_publisher_label":cell,"preload_kN_publisher_group":PRELOAD_KN[cell],
                "logger_file":g["logger"][0],"sp_files":len(g["sp"]),
                "logger_rows":len(logs),"logger_first":logs[0][0].isoformat(),
                "logger_last":logs[-1][0].isoformat(),
                "sp_first":mechanical[0][0].isoformat(),
                "sp_last":mechanical[-1][0].isoformat(),
                **integrate_signs(logs),**coupling,
                "time_and_same_cell_folder_join_pass":coupling["time_aligned_measurements"]>=2
            })
    return {
      "goal_key":"graz-20261123-real-same-cell-electro-mechanical-synchronization-v1",
      "source_doi":"10.5281/zenodo.22079387","source_sha256":hashlib.sha256(raw).hexdigest(),
      "original_md5":MD5,"raw_source_integrity_and_crc_verified":True,
      "physical_cells":results,"paired_cells":sum(x["time_and_same_cell_folder_join_pass"] for x in results),
      "paired_claim_scope":"same publisher folder and nearest timestamp <=3s; not metrology calibration",
      "static_mechanical_preload_not_impact":True,
      "signed_current_throughput_not_capacity_fade":True,
      "unique_one_specimen_per_preload_no_causal_comparison":True,
      "physical_safety_certification":False
    }

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="graz_paired_numeric_evidence.json")
    args=p.parse_args()
    result=audit()
    Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("GRAZ_REAL_FILE_TIMESERIES_PAIRED",result["paired_cells"],"OF",len(result["physical_cells"]))
    for c in result["physical_cells"]:
        print("CELL",c["physical_cell_publisher_label"],"LOG",c["logger_rows"],
              "SP_MATCH",c["time_aligned_measurements"],"SP_TOTAL",c["sp_measurements"],
              "AH_POS",c["positive_current_throughput_Ah"],
              "AH_NEG",c["negative_current_throughput_Ah"])

if __name__=="__main__":main()
