"""Source-native charge/rest context, never refit the frozen capacity model."""
import argparse
import collections
import hashlib
import io
import json
import math
import pathlib
import statistics
import urllib.request
import urllib.parse
import zipfile

import numpy as np
from scipy.io import loadmat

NAME = "3. Battery_Uniform_Distribution_Variable_Charge_Room_Temp_DataSet_2Post.zip"
URL = "https://zenodo.org/records/15277374/files/" + urllib.parse.quote(NAME) + "?download=1"
MD5 = "f7a4bd5502895073f362f09327b323af"
SHA = "4e757b8b4e574202c32702000e1002f7a235d1c83a5729cef584ce528f3a4859"
CELLS = {"RW1", "RW2", "RW7", "RW8"}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def vec(step, key):
    return np.asarray(step[key], dtype=float).ravel()

def summarize(step):
    result = {"comment": str(step["comment"]), "type": str(step["type"]), "date": str(step["date"])}
    for key in ("relativeTime", "time", "voltage", "current", "temperature"):
        a = vec(step, key)
        finite = a[np.isfinite(a)]
        result[key] = {
            "n": len(a), "finite": len(finite),
            "first": float(a[0]) if len(a) and np.isfinite(a[0]) else None,
            "last": float(a[-1]) if len(a) and np.isfinite(a[-1]) else None,
            "median": float(np.median(finite)) if len(finite) else None,
            "min": float(min(finite)) if len(finite) else None,
            "max": float(max(finite)) if len(finite) else None,
        }
    t = vec(step, "relativeTime")
    i = vec(step, "current")
    if len(t) == len(i) and len(t) > 1 and np.isfinite(t).all() and np.isfinite(i).all() and np.all(np.diff(t) >= 0):
        result["elapsed_s"] = float(t[-1] - t[0])
        result["signed_ah"] = float(np.trapezoid(i, t) / 3600)
    else:
        result["elapsed_s"] = None
        result["signed_ah"] = None
    return result

def preceding_charge(steps, j):
    # Never cross a discharge boundary to find a more convenient charge.
    for k in range(j-1, -1, -1):
        tag = str(steps[k]["comment"])
        if tag == "reference charge":
            return k
        if str(steps[k]["type"]) == "D":
            return None
    return None

def context(steps, j):
    s = steps[j]
    charge = preceding_charge(steps, j)
    summary = summarize(s)
    t, i, v = (vec(s,k) for k in ("relativeTime","current","voltage"))
    require(len(t)==len(i)==len(v) and len(t)>1, "reference shape")
    require(all(np.isfinite(x).all() for x in (t,i,v)) and np.all(np.diff(t)>=0), "reference waveform")
    require(t[-1]>t[0], "zero reference duration")
    q = float(np.trapezoid(i,t)/3600)
    q2 = math.fsum((b-a)*(c+d)/7200 for a,b,c,d in zip(t,t[1:],i,i[1:]))
    require(abs(q-q2)<1e-10, "independent integral")
    charge_summary = summarize(steps[charge]) if charge is not None else None
    between = [summarize(x) for x in steps[charge+1:j]] if charge is not None else []
    end_v = charge_summary["voltage"]["last"] if charge_summary else None
    end_i = charge_summary["current"]["last"] if charge_summary else None
    prev_v = summarize(steps[j-1])["voltage"]["last"] if j else None
    start_clock = summary["time"]["first"]
    end_clock = charge_summary["time"]["last"] if charge_summary else None
    gap = start_clock-end_clock if start_clock is not None and end_clock is not None else None
    return {
        "step_index": j, "reference": summary, "capacity_ah": q,
        "preceding_charge_index": charge, "preceding_charge": charge_summary,
        "intervening_steps": between, "charge_end_to_reference_start_s": gap,
        "charge_end_voltage_v": end_v, "charge_end_current_a": end_i,
        "preceding_step_end_voltage_v": prev_v,
        "reference_initial_voltage_v": float(v[0]),
        "preceding_end_minus_initial_v": prev_v-float(v[0]) if prev_v is not None else None,
        "charge_end_voltage_within_4p18_4p22": 4.18<=end_v<=4.22 if end_v is not None else None,
        "charge_end_abs_current_le_0p02": abs(end_i)<=.02 if end_i is not None else None,
        "prefix_samples": [{"relative_s":float(a),"voltage_v":float(b),"current_a":float(c)} for a,b,c in zip(t[:8],v[:8],i[:8])],
    }

def self_test():
    def step(comment, kind, v, i):
        return {"comment":comment,"type":kind,"date":"synthetic","relativeTime":[0,3600],"time":[0,3600],"voltage":v,"current":i,"temperature":[25,25]}
    charge=step("reference charge","C",[3.5,4.2],[-1,-.005])
    rest=step("rest post reference charge","R",[4.2,4.15],[0,0])
    dis=step("reference discharge","D",[4.05,3.2],[1,1])
    a=context([charge,rest,dis],2)
    require(a["preceding_charge_index"]==0 and len(a["intervening_steps"])==1,"charge/rest identification")
    require(a["capacity_ah"]==1 and a["charge_end_abs_current_le_0p02"],"integration and endpoint")
    require(abs(a["preceding_end_minus_initial_v"]-.1)<1e-10,"start drop")
    require(preceding_charge([charge,dis,dis],2) is None,"no boundary crossing")
    print("4 synthetic controls passed")

def main(out):
    req=urllib.request.Request(URL,headers={"User-Agent":"GKA-source-context-replay/1.0"})
    with urllib.request.urlopen(req,timeout=120) as r:
        raw=r.read()
    require(len(raw)==140923718 and hashlib.md5(raw).hexdigest()==MD5 and hashlib.sha256(raw).hexdigest()==SHA,"source identity")
    cells={}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        require(z.testzip() is None,"CRC")
        for name in sorted(n for n in z.namelist() if n.endswith(".mat")):
            cell=pathlib.PurePosixPath(name).stem
            b=z.read(name)
            steps=loadmat(io.BytesIO(b),simplify_cells=True)["data"]["step"]
            refs=[context(steps,j) for j,s in enumerate(steps) if str(s["comment"])=="reference discharge"]
            cells[cell]={"mat_sha256":hashlib.sha256(b).hexdigest(),"references":refs}
    require(set(cells)==CELLS,"physical cell population")
    require(sum(len(x["references"]) for x in cells.values())==197,"source reference count")
    summary={}
    for cell,x in cells.items():
        refs=x["references"]
        summary[cell]={
            "n":len(refs),
            "preceding_charge_found":sum(r["preceding_charge_index"] is not None for r in refs),
            "charge_end_voltage_pass":sum(r["charge_end_voltage_within_4p18_4p22"] is True for r in refs),
            "charge_end_current_pass":sum(r["charge_end_abs_current_le_0p02"] is True for r in refs),
            "first_two":refs[:2],
            "median_initial_v":statistics.median(r["reference_initial_voltage_v"] for r in refs),
            "min_initial_v":min(r["reference_initial_voltage_v"] for r in refs)
        }
    rw1=cells["RW1"]["references"]
    require(rw1[0]["step_index"]==3 and rw1[1]["step_index"]==5,"known anomalous row identity")
    require(abs(rw1[0]["reference_initial_voltage_v"]-4.009)<1e-9 and abs(rw1[0]["capacity_ah"]-2.0003486111111113)<1e-10,"known raw measurement identity")
    report={"status":"RAW_REFERENCE_CHARGE_REST_CONTEXT_AUDITED","source_sha256":SHA,"source_md5":MD5,"source_bytes":len(raw),"reference_count":197,"summary":summary,"cells":cells,"limits":["Preceding charge label and voltage/current endpoints do not prove equilibrium SOC or calibrated instrument accuracy.","0.02 A and 4.18-4.22 V are exploratory checks, not certified instrument tolerances.","No model change, causal aging inference, or production qualification."]}
    out=pathlib.Path(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2,allow_nan=False)
        f.write("\n")
    print(json.dumps({k:{a:b for a,b in v.items() if a!="first_two"} for k,v in summary.items()}))
    print("RW1 first two:",json.dumps(summary["RW1"]["first_two"]))
    print("SHA256",hashlib.sha256(out.read_bytes()).hexdigest())

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--output",default="evidence/GKA_NASA_RW3_RAW_CONTEXT_20261124.json")
    a=p.parse_args()
    if a.self_test:self_test()
    else:main(a.output)
