#!/usr/bin/env python3
"""NASA original measured-discharge capacity/time audit, separate from AGV field packs."""
import hashlib, io, json, math, pathlib, re, sys, urllib.request, zipfile
import numpy as np
from scipy.io import loadmat
URL="https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"
PRIMARY={"B0005","B0006","B0007","B0018"}
OPTIONAL={"B0025","B0026","B0027","B0028","B0045","B0046","B0047","B0048"}
TARGET=PRIMARY|OPTIONAL

def integrate(t,i,v,cutoff=2.7):
    t,i,v=(np.asarray(x,dtype=float).reshape(-1) for x in (t,i,v))
    if len(t)<2 or len(i)!=len(t) or len(v)!=len(t) or not np.isfinite(np.stack((t,i,v))).all() or np.any(np.diff(t)<=0):
        raise ValueError("invalid or nonmonotone waveform")
    # Sensor sign is determined by median nonzero current. Negative discharge convention.
    active=i[np.abs(i)>0.1]
    if len(active)<2: raise ValueError("no discharge current")
    sign=1 if np.median(active)>0 else -1
    signed=i*sign
    # signed net discharge, not absolute-current rectification.
    full=float(np.trapz(signed,t)/3600)
    dur=float(t[-1]-t[0])
    crossing=np.flatnonzero(v<=cutoff)
    if not len(crossing) or crossing[0]==0:
        return full,dur,None,None
    k=int(crossing[0])
    f=float((v[k-1]-cutoff)/(v[k-1]-v[k])) if v[k]!=v[k-1] else 1.0
    end=t[k-1]+f*(t[k]-t[k-1])
    end_i=signed[k-1]+f*(signed[k]-signed[k-1])
    q=float(np.trapz(np.r_[signed[:k],end_i],np.r_[t[:k],end])/3600)
    return full,dur,q,float(end-t[0])

def selftest():
    a=integrate([0,1800,3600],[-2,-2,-2],[4,3,2])
    assert abs(a[0]-2)<1e-12 and abs(a[2]-1.3)<1e-12 and abs(a[3]-2340)<1e-9,a
    b=integrate([0,900,1800],[-4,-4,-4],[4,3,2])
    assert abs(a[0]-b[0])<1e-12 and b[1]==a[1]/2
    c=integrate([0,1800,3600],[-1,-1,-1],[4,3,2])
    assert abs(a[0]-2*c[0])<1e-12 and a[1]==c[1]
    try:integrate([0,0],[-2,-2],[4,2])
    except ValueError:pass
    else:raise AssertionError("duplicate time accepted")
    assert integrate([0,1],[-2,-2],[4,3])[2] is None
    print("5/5 synthetic controls PASS")

def extract(zbytes, depth=0, lineage=""):
    if depth>4:raise ValueError("archive nesting too deep")
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        for m in z.infolist():
            name=pathlib.PurePosixPath(m.filename).name
            if m.is_dir():continue
            if name.lower().endswith(".zip"):
                yield from extract(z.read(m),depth+1,lineage+m.filename+"!")
            elif name.endswith(".mat") and name[:-4] in TARGET:
                yield name[:-4],z.read(m),lineage+m.filename

def stats(a):
    return {"n":len(a),"median":float(np.median(a)),"p95":float(np.percentile(a,95)),"max":float(np.max(a))} if len(a) else {"n":0}

def inspect(cell,raw,origin):
    mat=loadmat(io.BytesIO(raw),simplify_cells=True)[cell]
    rows=[]; skipped=[]; cycles=mat["cycle"]
    if isinstance(cycles,dict):cycles=[cycles]
    for k,c in enumerate(cycles):
        if c["type"]!="discharge":continue
        d=c["data"]
        try:
            capacity=float(d["Capacity"])
            if not math.isfinite(capacity) or capacity<=0:raise ValueError("invalid reported capacity")
            q,duration,q27,t27=integrate(d["Time"],d["Current_measured"],d["Voltage_measured"])
            rows.append({"cycle_index":k+1,"reported_capacity_Ah":capacity,"full_integral_Ah":q,
                         "full_seconds":duration,"at_2p7V_integral_Ah":q27,"at_2p7V_seconds":t27,
                         "mean_discharge_A":q*3600/duration,
                         "full_error_pct":100*abs(q-capacity)/capacity,
                         "cutoff_error_pct":100*abs(q27-capacity)/capacity if q27 is not None else None,
                         "fixed_2A_time_error_pct":100*abs(2*duration/3600-capacity)/capacity})
        except (ValueError,KeyError,TypeError) as e:skipped.append({"cycle_index":k+1,"reason":str(e)})
    if not rows:raise ValueError("no valid cycles: "+cell)
    return {"mat_sha256":hashlib.sha256(raw).hexdigest(),"source_member":origin,"source_bytes":len(raw),
            "discharge_cycles":len(rows)+len(skipped),"valid":len(rows),"excluded":skipped,
            "full_integral_absolute_relative_error_pct":stats([r["full_error_pct"] for r in rows]),
            "cutoff_2p7V_integral_absolute_relative_error_pct":stats([r["cutoff_error_pct"] for r in rows if r["cutoff_error_pct"] is not None]),
            "fixed_2A_duration_absolute_relative_error_pct":stats([r["fixed_2A_time_error_pct"] for r in rows]),
            "median_mean_discharge_A":float(np.median([r["mean_discharge_A"] for r in rows])),
            "cycles":rows}

def main():
    selftest()
    if "--selftest" in sys.argv:return
    with urllib.request.urlopen(urllib.request.Request(URL,headers={"User-Agent":"CANO-source-audit/1.0"}),timeout=180) as f:
        raw=f.read(600_000_001)
    if len(raw)>600_000_000:raise ValueError("source exceeds size bound")
    sources={}
    for cell,mat,path in extract(raw):
        if cell in sources:
            if sources[cell]["mat_sha256"]!=hashlib.sha256(mat).hexdigest():raise ValueError("conflicting source duplicates: "+cell)
            continue
        sources[cell]=inspect(cell,mat,path)
    if not PRIMARY.issubset(sources):raise ValueError("missing classic source cells: "+str(PRIMARY-sources.keys()))
    allrows=[(name,r) for name,s in sources.items() for r in s["cycles"] if r["reported_capacity_Ah"]>=0.2 and r["mean_discharge_A"]>0.1]
    # Actual observed near-equal-capacity pairs, distinct cells, very different durations;
    # report only the strongest case under a predeclared 2% capacity match and 1.5x duration threshold.
    allrows.sort(key=lambda x:x[1]["reported_capacity_Ah"])
    best=None
    for j,(name,a) in enumerate(allrows):
        for name2,b in allrows[j+1:]:
            if b["reported_capacity_Ah"]>1.02*a["reported_capacity_Ah"]:break
            if name==name2:continue
            ratio=max(a["full_seconds"],b["full_seconds"])/min(a["full_seconds"],b["full_seconds"])
            if ratio>=1.5 and (best is None or ratio>best["duration_ratio"]):
                best={"duration_ratio":ratio,"a":{"cell":name,**a},"b":{"cell":name2,**b}}
    receipt={"status":"NASA_PCOE_ORIGINAL_DISCHARGE_WAVEFORM_AUDIT","url":URL,"archive_sha256":hashlib.sha256(raw).hexdigest(),
             "archive_bytes":len(raw),"source_cells":sources,"equal_capacity_different_duration_example":best,
             "pair_rule":"distinct cells; reported capacities within 2%; full-duration ratio >=1.5; max ratio; descriptive not causal",
             "limits":"Reported capacity is publisher reference, may be derived from same signals; cutoff protocols differ; no AGV FB-pack identity or SoH claim; no independent sensor calibration."}
    pathlib.Path("NASA_AGV_CAPACITY_EVIDENCE.json").write_text(json.dumps(receipt,indent=2,allow_nan=False))
    print(json.dumps({"cells":{c:{k:v for k,v in s.items() if k not in ("cycles","excluded")} for c,s in sources.items()},"example":best},indent=2))
if __name__=="__main__":main()
