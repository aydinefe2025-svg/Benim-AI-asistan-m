"""Source-pinned NASA RW2 prospective checkpoint prediction, not AGV SoH."""
import argparse, hashlib, io, json, math, pathlib, statistics, urllib.request, zipfile
import numpy as np
from scipy.io import loadmat
from collections import defaultdict, Counter

MD5 = "aa53dce833e0ce7ee75376846dec4e59"
SHA = "18bf47337577e07872919327a6ee994adc59e33fd2901d69c5911c26102837b8"
URL = "https://zenodo.org/records/15277374/files/2.%20Battery_Uniform_Distribution_Discharge_Room_Temp_DataSet_2Post.zip?download=1"
CELLS = {"RW3","RW4","RW5","RW6"}
def need(ok,msg):
    if not ok: raise ValueError(msg)
def integrate(s):
    t,i,v=[np.asarray(s[k],float).ravel() for k in ("relativeTime","current","voltage")]
    need(len(t)==len(i)==len(v)>1,"shape")
    need(all(np.isfinite(x).all() for x in (t,i,v)),"finite")
    need(np.all(np.diff(t)>=0) and t[-1]>t[0],"clock")
    need(np.min(i)>=-.05,"current sign")
    q=math.fsum(float(dt)*(float(a)+float(b))/7200 for dt,a,b in zip(np.diff(t),i[:-1],i[1:]))
    return (q,float(t[-1]-t[0]),float(np.median(i)),float(v[0]),float(v[-1]))
def extract(steps,cell):
    refs=defaultdict(list); cycles=defaultdict(list); reject=Counter()
    group=0; seen=False; pending=[]; invalid=False
    def flush():
        nonlocal pending,invalid
        if invalid: reject["invalid_waveform"]+=1
        elif pending:
            if pending[0][3]<3.7 or pending[-1][4]>3.22: reject["endpoint"]+=1
            elif any(not .45<=s[2]<=4.1 for s in pending): reject["load"]+=1
            else: cycles[group].append((sum(s[0] for s in pending),sum(s[1] for s in pending)))
        pending=[];invalid=False
    for s in steps:
        tag=s["comment"]
        if tag not in ("discharge (random walk)","rest (random walk)"):flush()
        if tag=="reference discharge":
            if seen:group+=1;seen=False
            q,t,i,v0,v1=integrate(s)
            need(s["type"]=="D" and .95<=i<=1.05 and 3.9<=v0<=4.3 and 3.15<=v1<=3.25,"reference protocol")
            refs[group].append(q)
        elif tag=="discharge (random walk)":
            seen=True
            need(s["type"]=="D","RW type")
            try:pending.append(integrate(s))
            except ValueError:invalid=True
    flush()
    need(all(len(v)==2 for v in refs.values()),"two references")
    rows=[]
    for k in sorted(refs):
        if k+1 not in refs or len(cycles[k])<10:continue
        prev,nextq=statistics.mean(refs[k]),statistics.mean(refs[k+1])
        spread=max(abs(refs[j][0]-refs[j][1])/statistics.mean(refs[j]) for j in (k,k+1))
        q=statistics.median(v[0] for v in cycles[k]);t=statistics.median(v[1] for v in cycles[k])
        need(min(prev,nextq,q,t)>0,"positive")
        rows.append(dict(cell=cell,checkpoint=k,prev_ah=prev,next_ah=nextq,n=len(cycles[k]),
            duration_s=t,median_rw_ah=q,spread=spread,
            y=math.log(nextq/prev),duration_x=math.log(t*2/3600/prev),charge_x=math.log(q/prev)))
    return rows,dict(reference_count=sum(map(len,refs.values())),checkpoints=len(refs),accepted=sum(map(len,cycles.values())),rejected=dict(reject))
def evaluate(rows):
    # Training exclusively other physical cells. Previous reference is observed before block.
    out={}
    for model,feature in (("persistence",None),("mean_change",None),("duration","duration_x"),("charge","charge_x")):
        pred=[]
        for cell in sorted({r["cell"] for r in rows}):
            train=[r for r in rows if r["cell"]!=cell];test=[r for r in rows if r["cell"]==cell]
            need(train and test,"fold support")
            if model=="persistence": intercept=0.;slope=0.
            elif feature is None:intercept=statistics.mean(r["y"] for r in train);slope=0.
            else:
                x=np.array([r[feature] for r in train]);y=np.array([r["y"] for r in train])
                need(np.ptp(x)>1e-12,"constant predictor")
                intercept,slope=map(float,np.linalg.lstsq(np.column_stack((np.ones(len(x)),x)),y,rcond=None)[0])
            for r in test:
                estimate=r["prev_ah"]*math.exp(intercept+(slope*r[feature] if feature else 0))
                pred.append(dict(cell=cell,checkpoint=r["checkpoint"],actual_ah=r["next_ah"],predicted_ah=estimate,error_ah=estimate-r["next_ah"]))
        per={c:math.sqrt(statistics.mean(p["error_ah"]**2 for p in pred if p["cell"]==c)) for c in sorted({p["cell"] for p in pred})}
        out[model]={"rmse_ah":math.sqrt(statistics.mean(p["error_ah"]**2 for p in pred)),"per_cell_rmse_ah":per,"predictions":pred}
    return out
def controls():
    assert integrate({"relativeTime":[0,3600],"current":[1,1],"voltage":[4.2,3.2]})[:2]==(1.,3600.)
    try:integrate({"relativeTime":[2,1],"current":[1,1],"voltage":[4.2,3.2]})
    except ValueError:pass
    else:raise AssertionError("reversed clock accepted")
    rows=[dict(cell=c,checkpoint=i,prev_ah=2.,next_ah=2*math.exp(.1*i),y=.1*i,duration_x=float(i),charge_x=float(i)) for c in ("A","B","C") for i in (1,2,3)]
    e=evaluate(rows)
    assert e["duration"]["rmse_ah"]<1e-12 and e["persistence"]["rmse_ah"]>0
    assert len(e["duration"]["predictions"])==9
    return 4
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--archive",type=pathlib.Path);ap.add_argument("--output",type=pathlib.Path,required=True);ap.add_argument("--self-test",action="store_true");args=ap.parse_args()
    n=controls()
    if args.self_test:print("4/4 synthetic checks passed");return
    if args.archive:b=args.archive.read_bytes()
    else:
        with urllib.request.urlopen(urllib.request.Request(URL,headers={"User-Agent":"GKA-scientific-replay/1.0"}),timeout=120) as r:b=r.read(121_000_000)
    need(len(b)==120125009 and hashlib.md5(b).hexdigest()==MD5 and hashlib.sha256(b).hexdigest()==SHA,"publisher archive hash")
    rows=[];counts={}
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        need(z.testzip() is None,"CRC")
        for path in sorted(x for x in z.namelist() if x.endswith(".mat")):
            c=pathlib.PurePosixPath(path).stem
            new,counts[c]=extract(loadmat(io.BytesIO(z.read(path)),simplify_cells=True)["data"]["step"],c);rows.extend(new)
    need(set(counts)==CELLS and sum(v["reference_count"] for v in counts.values())==146,"population")
    need(sum(v["accepted"] for v in counts.values())==2573 and sum(sum(v["rejected"].values()) for v in counts.values())==131,"prior RW count reconciliation")
    clean=[r for r in rows if r["spread"]<=.02]
    need(set(r["cell"] for r in clean)==CELLS,"all cells supported")
    result={"status":"NASA_RW2_PROSPECTIVE_CHECKPOINT_LOCO_EVALUATED","source_md5":MD5,"source_sha256":SHA,"counts":counts,"controls":n,"all_pairs":len(rows),"clean_pairs":len(clean),"all":evaluate(rows),"sensitivity":evaluate(clean),"rows":rows,"limits":["Predict next measured reference capacity from prior reference and intervening completed observed RW block; no next-reference feature leakage.","Leave-one-physical-cell-out, four cells only; no external AGV transfer or instrument calibration. Median duration proxy uses fixed 2 A scale, not assumed actual reference current.","Paired reference spread >2% sensitivity excludes adjacent intervals retrospectively; not a deployable prospective filter.","Relative duration and Ah proxies are descriptive, not causal. Active time excludes inter-step gaps."]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,allow_nan=False);f.write("\n")
    print(json.dumps({"counts":counts,"all_pairs":len(rows),"clean_pairs":len(clean),"models":{key:{m:{k:v for k,v in s.items() if k!="predictions"} for m,s in result[key].items()} for key in ("all","sensitivity")}},indent=2))
if __name__=="__main__":main()
