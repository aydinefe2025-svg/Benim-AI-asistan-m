"""Prospectively fixed V0 ablation vs V1, untouched NASA group 5."""
import argparse, collections, hashlib, io, json, math, pathlib, urllib.parse, urllib.request, zipfile
import numpy as np
from scipy.io import loadmat

NAME="5. RW_Skewed_High_Room_Temp_DataSet_2Post.zip"
MD5="9a0fabc687ae3a8d990c9d6f2f0412d4"
EXPECTED={"RW17","RW18","RW19","RW20"}
TRAINED={"RW3","RW4","RW5","RW6"}
DEVELOPMENT={"RW1","RW2","RW7","RW8"}
V1_SHA="8bee62d00fdc6d60b36e5bd22cc4dec13a3d84073115e2c6c4de72093ba89f53"
MU=[4.094972602739726,0.11468493150684936,0.03712328767123288]
SCALE=[0.008107112728178259,0.027635532375057302,0.007975897262153283]
COEF=[0.03375016766851486,-0.03672125309735591,-0.17344430269662295]
INTERCEPT=1.5413766938736684
GATE={"rmse_max_ah":.1,"fraction_within_0p1ah_all_groups_min":.9,"per_cell_rmse_max_ah":.15,"coverage_min":.9}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def predict(x,ablate):
    z=[(a-b)/s for a,b,s in zip(x,MU,SCALE)]
    return INTERCEPT+math.fsum(z[j]*COEF[j] for j in range(1 if ablate else 0,3))
def prefix(t,v,i):
    t,v,i=[np.asarray(x,float).ravel() for x in (t,v,i)]
    require(len(t)==len(v)==len(i) and len(t)>2,"shape")
    require(np.isfinite(t[0]) and 0<=t[0]<=1,"first sample")
    t=t-t[0]
    end=int(np.searchsorted(t,300,side="left"))
    require(end<len(t),"short prefix")
    t,v,i=[a[:end+1] for a in (t,v,i)]
    require(all(np.isfinite(a).all() for a in (t,v,i)) and np.all(np.diff(t)>0),"prefix clock")
    require(max(np.diff(t))<=20 and .95<=np.median(i)<=1.05,"prefix protocol")
    require(i.min()>=.9 and i.max()<=1.1,"prefix current")
    a,b,c=np.interp([0,150,300],t,v)
    return [float(a),float(a-b),float(b-c)]
def reference(s):
    require(s["type"]=="D","reference type")
    t,v,i=[np.asarray(s[k],float).ravel() for k in ("relativeTime","voltage","current")]
    x=prefix(t,v,i)
    require(all(np.isfinite(a).all() for a in (t,v,i)) and np.all(np.diff(t)>=0) and t[-1]>t[0],"full waveform")
    require(i.min()>=.9 and i.max()<=1.1 and 3.9<=v[0]<=4.3 and 3.15<=v[-1]<=3.25,"full protocol")
    q=float(np.trapezoid(i,t)/3600)
    q2=math.fsum((b-a)*(c+d)/7200 for a,b,c,d in zip(t,t[1:],i,i[1:]))
    require(abs(q-q2)<1e-10,"integration")
    temp=np.asarray(s["temperature"],float).ravel()
    temperature_ok=bool(len(temp)==len(t) and np.isfinite(temp).all() and temp.min()>=-20 and temp.max()<=80)
    return {"x":x,"actual_ah":q,"v1":predict(x,False),"ablation":predict(x,True),"mean":INTERCEPT,"temperature_ok":temperature_ok,"temperature_start_c":float(temp[0]) if len(temp) and np.isfinite(temp[0]) else None}

def protocol_profile(s):
    t,v,i,temp=[np.asarray(s[k],float).ravel() for k in ("relativeTime","voltage","current","temperature")]
    def finite_summary(a):
        b=a[np.isfinite(a)]
        return {"n":len(a),"finite":len(b),"median":float(np.median(b)) if len(b) else None,"min":float(b.min()) if len(b) else None,"max":float(b.max()) if len(b) else None,"first":float(a[0]) if len(a) and np.isfinite(a[0]) else None,"last":float(a[-1]) if len(a) and np.isfinite(a[-1]) else None}
    prefix_i=i[(t-t[0])<=300] if len(t)==len(i) and len(t) else np.array([])
    dt=np.diff(t[(t-t[0])<=300]) if len(t) else np.array([])
    return {"type":str(s["type"]),"date":str(s["date"]),"current_a":finite_summary(i),"prefix_current_a":finite_summary(prefix_i),"prefix_dt_s":finite_summary(dt),"voltage_v":finite_summary(v),"temperature_c":finite_summary(temp),"duration_s":float(t[-1]-t[0]) if len(t)>1 and np.isfinite(t[[0,-1]]).all() else None}

def groups(steps):
    out=[];g=[];rw=False
    for j,s in enumerate(steps):
        if s["comment"]=="discharge (random walk)":rw=True
        if s["comment"]=="reference discharge":
            if rw and g:out.append(g);g=[]
            rw=False;g.append((j,s))
    if g:out.append(g)
    return out
def metrics(rows,key,total):
    if not rows:return {"n":0,"coverage":0,"rmse_ah":None,"within_all_fraction":0,"within_0p1ah":0}
    e=[r[key]-r["actual_ah"] for r in rows]
    good=sum(abs(x)<=.1 for x in e)
    return {"n":len(e),"coverage":len(e)/total,"rmse_ah":math.sqrt(math.fsum(x*x for x in e)/len(e)),"mae_ah":math.fsum(abs(x) for x in e)/len(e),"bias_ah":math.fsum(e)/len(e),"max_abs_ah":max(map(abs,e)),"within_0p1ah":good,"within_all_fraction":good/total}
def controls():
    require(abs(predict(MU,False)-INTERCEPT)<1e-12,"centering")
    x=MU.copy();x[0]-=.1
    require(abs(predict(x,True)-predict(MU,True))<1e-12 and predict(x,False)!=predict(MU,False),"offset invariance")
    t=np.arange(0,601,10);v=4.2-t*.0001;i=np.ones(len(t));x=prefix(t,v,i)
    v[t>310]=0;i[t>310]=999
    require(np.allclose(prefix(t,v,i),x),"future invariance")
    require(metrics([{"actual_ah":1,"v1":1}],"v1",2)["within_all_fraction"]==.5,"abstention denominator")
    require(len(groups([{"comment":"reference discharge"},{"comment":"reference discharge"},{"comment":"discharge (random walk)"},{"comment":"reference discharge"}]))==2,"group boundary")
    print("5 synthetic controls passed")
def main(out):
    require(not EXPECTED&(TRAINED|DEVELOPMENT),"population leakage")
    req=urllib.request.Request("https://zenodo.org/records/15277374/files/"+urllib.parse.quote(NAME)+"?download=1",headers={"User-Agent":"GKA-external-frozen-ablation/1.0"})
    with urllib.request.urlopen(req,timeout=120) as f:raw=f.read()
    require(hashlib.md5(raw).hexdigest()==MD5,"publisher hash")
    rows=[];rejected=[];inventory={};secondary=[];protocol=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        require(z.testzip() is None,"CRC")
        for n in sorted(x for x in z.namelist() if x.endswith(".mat")):
            c=pathlib.PurePosixPath(n).stem;b=z.read(n)
            steps=loadmat(io.BytesIO(b),simplify_cells=True)["data"]["step"];gg=groups(steps)
            require(gg,"reference groups absent")
            inventory[c]={"mat_sha256":hashlib.sha256(b).hexdigest(),"groups":len(gg),"raw_references":sum(map(len,gg)),"group_sizes":dict(collections.Counter(map(len,gg)))}
            for k,g in enumerate(gg):
                for rep,(j,s) in enumerate(g):
                    ident={"cell":c,"checkpoint":k,"step":j,"repeat":rep+1}
                    protocol.append(ident|protocol_profile(s))
                    try:r=reference(s)
                    except ValueError as e:rejected.append(ident|{"reason":str(e)});continue
                    (rows if rep==0 else secondary).append(ident|r)
    require(set(inventory)==EXPECTED,"external population mismatch")
    total=sum(x["groups"] for x in inventory.values())
    require(len(rows)+len(secondary)+len(rejected)==sum(x["raw_references"] for x in inventory.values()),"reference accounting")
    allm={key:metrics(rows,key,total) for key in ("mean","v1","ablation")}
    by={c:{key:metrics([r for r in rows if r["cell"]==c],key,inventory[c]["groups"]) for key in ("v1","ablation")} for c in sorted(EXPECTED)}
    a=allm["ablation"]
    gate={"coverage":a["coverage"]>=GATE["coverage_min"],"rmse":a["rmse_ah"] is not None and a["rmse_ah"]<=GATE["rmse_max_ah"],"tolerance":a["within_all_fraction"]>=GATE["fraction_within_0p1ah_all_groups_min"],"per_cell":all(x["ablation"]["rmse_ah"] is not None and x["ablation"]["rmse_ah"]<=GATE["per_cell_rmse_max_ah"] for x in by.values())}
    require(len(protocol)==sum(x["raw_references"] for x in inventory.values()),"protocol accounting")
    report={"protocol_profiles":protocol,"status":"EXTERNAL_ABLATION_GATE_PASS" if all(gate.values()) else "EXTERNAL_ABLATION_GATE_NOT_MET","source_md5":MD5,"source_sha256":hashlib.sha256(raw).hexdigest(),"source_bytes":len(raw),"v1_model_sha256":V1_SHA,"frozen_coefficients":{"mean":MU,"scale":SCALE,"coef":COEF,"intercept":INTERCEPT,"ablation_coef":[0,*COEF[1:]]},"gate_definition":GATE,"gate":gate,"inventory":inventory,"primary_groups":total,"metrics":allm,"per_cell":by,"valid_temperature_subset":{key:metrics([r for r in rows if r["temperature_ok"]],key,total) for key in ("v1","ablation")},"rows":rows,"secondary":secondary,"rejected":rejected,"limits":["No fitting or parameter selection on group 5. Ablation selected on previously examined group 3. Same NASA program, not a separate lab.","NASA catalog title says high temperature but archive filename says room temperature; actual recorded temperature reported, not inferred from title.","First reference per contiguous group, no replacement for exclusions. Full waveform QC is retrospective. Out-of-protocol first references counted against total tolerance and coverage.","Temperature screen is a broad plausibility check, not calibration; no causal claim or AGV transfer."]}
    p=pathlib.Path(out);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("x",encoding="utf8") as f:json.dump(report,f,indent=2,allow_nan=False);f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("rows","secondary","rejected","protocol_profiles")}|{"rejection_counts":dict(collections.Counter(x["reason"] for x in rejected)),"report_sha256":hashlib.sha256(p.read_bytes()).hexdigest()}))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",default="evidence/GKA_NASA_RW5_FROZEN_ABLATION_20261124.json");a=p.parse_args()
    if a.self_test:controls()
    else:main(a.output)
