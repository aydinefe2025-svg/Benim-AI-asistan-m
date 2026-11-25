"""Separate 30-second cadence compatibility study. Frozen models; no refit."""
import argparse
import collections
import hashlib
import io
import json
import math
import pathlib
import urllib.parse
import urllib.request
import zipfile

import numpy as np
from scipy.io import loadmat
import gka_nasa_rw5_frozen_ablation as base

TRAIN_NAME = "2. Battery_Uniform_Distribution_Discharge_Room_Temp_DataSet_2Post.zip"
TRAIN_MD5 = "aa53dce833e0ce7ee75376846dec4e59"
TRAIN_SHA = "18bf47337577e07872919327a6ee994adc59e33fd2901d69c5911c26102837b8"
TEST_SHA = "ad7feba63b1e1d1a3ac87b86f5918725a124538e0438dfe7253e705a39937f75"
ANCHOR_TOL_S = .5
MAX_GRID_GAP_S = 30.5
BRIDGE_MAX_PREDICTOR_DELTA_AH = .005

def require(ok, msg):
    if not ok:
        raise ValueError(msg)

def load_archive(name, md5, sha):
    url = "https://zenodo.org/records/15277374/files/" + urllib.parse.quote(name) + "?download=1"
    req = urllib.request.Request(url, headers={"User-Agent": "GKA-cadence-bridge/1.0"})
    with urllib.request.urlopen(req, timeout=120) as f:
        raw = f.read()
    require(hashlib.md5(raw).hexdigest() == md5 and hashlib.sha256(raw).hexdigest() == sha, "source identity")
    return raw

def samples_on_grid(t, v, i):
    """Use recorded points, never synthetic resampling; allow 0.5 s clock tolerance."""
    t, v, i = [np.asarray(x, float).ravel() for x in (t, v, i)]
    require(len(t) == len(v) == len(i) and len(t) > 2, "shape")
    require(np.isfinite(t[0]) and 0 <= t[0] <= 1, "first sample")
    elapsed = t - t[0]
    end = int(np.searchsorted(elapsed, 300 + ANCHOR_TOL_S, side="right"))
    elapsed, v, i = [x[:end] for x in (elapsed, v, i)]
    require(all(np.isfinite(x).all() for x in (elapsed, v, i)) and np.all(np.diff(elapsed) > 0), "prefix clock")
    require(len(elapsed) > 1 and max(np.diff(elapsed)) <= MAX_GRID_GAP_S, "prefix cadence")
    require(.95 <= np.median(i) <= 1.05 and i.min() >= .9 and i.max() <= 1.1, "prefix current")
    grid = np.arange(0., 301., 30.)
    idx = [int(np.argmin(abs(elapsed - k))) for k in grid]
    require(len(set(idx)) == len(grid), "duplicate grid sample")
    require(max(abs(elapsed[j] - k) for j, k in zip(idx, grid)) <= ANCHOR_TOL_S, "missing grid anchor")
    return elapsed[idx], v[idx], i[idx]

def grid_features(t,v,i):
    tt,vv,ii = samples_on_grid(t,v,i)
    return [float(vv[0]), float(vv[0]-vv[5]), float(vv[5]-vv[10])], float(tt[-1])

def reference30(s):
    require(str(s["type"]) == "D", "reference type")
    t, v, i = [np.asarray(s[k],float).ravel() for k in ("relativeTime","voltage","current")]
    x, end = grid_features(t,v,i)
    require(all(np.isfinite(a).all() for a in (t,v,i)) and np.all(np.diff(t)>=0) and t[-1]>t[0], "full waveform")
    require(i.min()>=.9 and i.max()<=1.1 and 3.9<=v[0]<=4.3 and 3.15<=v[-1]<=3.25, "full protocol")
    q = float(np.trapezoid(i,t)/3600)
    q2 = math.fsum((b-a)*(c+d)/7200 for a,b,c,d in zip(t,t[1:],i,i[1:]))
    require(abs(q-q2)<1e-10, "integration")
    temp = np.asarray(s["temperature"],float).ravel()
    tok = bool(len(temp)==len(t) and np.isfinite(temp).all() and temp.min()>=-20 and temp.max()<=80)
    return {"x":x,"last_observed_elapsed_s":end,"actual_ah":q,"v1":base.predict(x,False),"ablation":base.predict(x,True),"mean":base.INTERCEPT,"temperature_ok":tok}

def controls():
    t=np.arange(0,601,10.);v=4.2-.0001*t;i=np.ones(len(t))
    x,_=grid_features(t,v,i)
    x2,_=grid_features(t[::3],v[::3],i[::3])
    require(np.allclose(x,x2) and np.allclose(x,[4.2,.015,.015]), "grid equivalence")
    v[t>301]=0;i[t>301]=999
    require(np.allclose(grid_features(t,v,i)[0],x), "future invariance")
    for bad in (np.arange(0,601,60.), np.arange(0,280,30.)):
        try:grid_features(bad,4.2-.0001*bad,np.ones(len(bad)))
        except ValueError:continue
        raise AssertionError("unsupported cadence accepted")
    require(base.metrics([{"v1":1.0,"actual_ah":1.0}],"v1",2)["within_all_fraction"]==.5,"denominator")
    print("5 cadence controls passed")

def read_cells(raw,expected):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        require(z.testzip() is None, "CRC")
        names=[n for n in z.namelist() if n.endswith(".mat")]
        require({pathlib.PurePosixPath(n).stem for n in names}==expected and len(names)==len(expected),"cell population")
        for n in sorted(names):
            b=z.read(n)
            yield pathlib.PurePosixPath(n).stem,hashlib.sha256(b).hexdigest(),loadmat(io.BytesIO(b),simplify_cells=True)["data"]["step"]

def bridge():
    raw=load_archive(TRAIN_NAME,TRAIN_MD5,TRAIN_SHA)
    rows=[];errors=[]
    for cell,sha,steps in read_cells(raw,base.TRAINED):
        for k,g in enumerate(base.groups(steps)):
            j,s=g[0]
            try:
                old=base.reference(s)
                tt,vv,ii=samples_on_grid(s["relativeTime"],s["voltage"],s["current"])
                # Decimate the original recorded points and run the identical native-grid extractor.
                new,_=grid_features(tt,vv,ii)
                d1=abs(base.predict(new,False)-old["v1"])
                d2=abs(base.predict(new,True)-old["ablation"])
                rows.append({"cell":cell,"checkpoint":k,"step":j,"mat_sha256":sha,"original_x":old["x"],"coarse_x":new,"v1_delta_ah":d1,"ablation_delta_ah":d2})
            except ValueError as e:
                errors.append({"cell":cell,"checkpoint":k,"step":j,"reason":str(e)})
    require(len(rows)+len(errors)==73,"training population")
    mx=max((max(r["v1_delta_ah"],r["ablation_delta_ah"]) for r in rows),default=None)
    return {"total":73,"n":len(rows),"max_prediction_delta_ah":mx,"threshold_ah":BRIDGE_MAX_PREDICTOR_DELTA_AH,"pass":len(rows)==73 and mx is not None and mx<=BRIDGE_MAX_PREDICTOR_DELTA_AH,"rows":rows,"errors":errors}

def main(output):
    controls()
    b=bridge()
    raw=load_archive(base.NAME,base.MD5,TEST_SHA)
    rows=[];secondary=[];rejected=[];inventory={}
    for cell,sha,steps in read_cells(raw,base.EXPECTED):
        gg=base.groups(steps)
        inventory[cell]={"groups":len(gg),"raw_references":sum(map(len,gg)),"mat_sha256":sha}
        for k,g in enumerate(gg):
            for rep,(j,s) in enumerate(g):
                ident={"cell":cell,"checkpoint":k,"step":j,"repeat":rep+1}
                try:r=reference30(s)
                except ValueError as e:rejected.append(ident|{"reason":str(e)});continue
                (rows if rep==0 else secondary).append(ident|r)
    total=sum(x["groups"] for x in inventory.values())
    require(total==111 and len(rows)+len(secondary)+len(rejected)==113,"external population accounting")
    m={key:base.metrics(rows,key,total) for key in ("mean","v1","ablation")}
    by={c:{key:base.metrics([r for r in rows if r["cell"]==c],key,inventory[c]["groups"]) for key in ("v1","ablation")} for c in sorted(base.EXPECTED)}
    a=m["ablation"];g=base.GATE
    gate={"bridge":b["pass"],"coverage":a["coverage"]>=g["coverage_min"],"rmse":a["rmse_ah"] is not None and a["rmse_ah"]<=g["rmse_max_ah"],"tolerance":a["within_all_fraction"]>=g["fraction_within_0p1ah_all_groups_min"],"per_cell":all(x["ablation"]["rmse_ah"] is not None and x["ablation"]["rmse_ah"]<=g["per_cell_rmse_max_ah"] for x in by.values())}
    report={"status":"EXPLORATORY_CADENCE_BRIDGE_GATE_PASS" if all(gate.values()) else "EXPLORATORY_CADENCE_BRIDGE_GATE_NOT_MET","train_source_sha256":TRAIN_SHA,"test_source_sha256":TEST_SHA,"v1_model_sha256":base.V1_SHA,"bridge":b,"primary_groups":total,"inventory":inventory,"metrics":m,"per_cell":by,"gate":gate,"gate_definition":g,"rows":rows,"secondary":secondary,"rejected":rejected,"temperature_plausible_primary_count":sum(r["temperature_ok"] for r in rows),"limits":["30-second compatibility study selected after original source QC rejected all rows; original zero-coverage acceptance failure is preserved.","No new fitting, parameter tuning or threshold change. Decimation comparison uses training cells, not independent instrument validation.","Grid uses real recorded samples within 0.5 s of 0,30,...,300 s; results available by 300.5 s. Full waveform label QC is retrospective.","Mislabelled rest and other first-reference rejections stay in total denominator. Temperature plausibility is not calibration.","Same NASA program. Not AGV transfer, production acceptance or independent prospective replication."]}
    p=pathlib.Path(output);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("x",encoding="utf8") as f:json.dump(report,f,indent=2,allow_nan=False);f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("rows","secondary","rejected","bridge")}|{"bridge_summary":{k:v for k,v in b.items() if k!="rows"},"rejection_counts":dict(collections.Counter(x["reason"] for x in rejected)),"report_sha256":hashlib.sha256(p.read_bytes()).hexdigest()}))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",default="evidence/GKA_NASA_RW5_CADENCE_BRIDGE_20261124.json");a=p.parse_args()
    if a.self_test:controls()
    else:main(a.output)
