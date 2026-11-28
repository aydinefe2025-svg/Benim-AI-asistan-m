"""Replay fixed V4 and exploratory V5 on the original RW1 archive. No refitting."""
import argparse,collections,gc,hashlib,io,json,math,pathlib,tempfile,urllib.parse,urllib.request,zipfile
import numpy as np
from scipy.io import loadmat
NAME="1. Battery_Uniform_Distribution_Charge_Discharge_DataSet_2Post.zip"
SHA="b4bdaf590b45c2e784174d1ad6e1556cac7b806fe5c0472092112fba46e96675"
MD5="4c140b2223fbd31c5f17f6c4ff470d9e"
V4_SHA="82209dcd776b5bd7cfef4f67c1222eccea9dd591b5f42000423a2a782a4a02fd"
V5_SHA="6da376037acc70064307749dd6b5b76f6e4ddb16e2a73d43e50a5115392735d7"
V4=([0.10117358490566052,0.03329811320754718,0.027283018867924523,0.02489433962264149,0.023249056603773584,0.0219698113207547],[0.04005901378293849,0.009906629961532422,0.006260319355560545,0.00463255156451217,0.0035488835683495728,0.0027097019891605205],[-0.043319949158009186,0.013377051576286606,0.05111411764861024,-0.0634070346863225,-0.14226955086017337,-0.08908684623326371],1.6521368764570232)
LIN=([0.10820845070422545,0.035335211267605644,0.028557746478873245,0.025842253521126738,0.024039436619718323,0.022614084507042224],[0.04305491333620838,0.010986176956079674,0.006956113168616513,0.005166840699011974,0.004037656511534616,0.0031712305238049093],[-0.03834878443763922,0.028035113272290687,0.03355040149328761,-0.0816471364635301,-0.1521559577252113,-0.10295869434502229],1.592123462339593)
INV=([42.542083005257794,1.2989277984131125,4.322531006234248],[6.936681775909886,0.1474397931858656,1.0762129271770366],[0.2824626534894839,-0.06078826674271232,0.03380396008981558],1.592123462339593)
def req(ok,msg):
 if not ok:raise ValueError(msg)
def pred(x,m):
 mu,sd,c,b=m
 return b+math.fsum((a-u)/s*w for a,u,s,w in zip(x,mu,sd,c))
def shape(d):
 late=float(np.mean(d[3:]))
 req(late>0,"nonpositive late slope")
 return [1/late,float(np.mean(d[1:3]))/late,d[0]/late]
def prefix(t,v,i):
 t,v,i=[np.asarray(a,float).ravel() for a in (t,v,i)]
 req(len(t)==len(v)==len(i) and len(t)>2 and 0<=t[0]<=1,"shape/clock")
 e=t-t[0];hits=np.flatnonzero(np.isfinite(e)&(e>=899.5))
 req(len(hits)>0,"short");j=int(hits[0]);u,vol,cur=e[:j+1],v[:j+1],i[:j+1]
 req(all(np.isfinite(a).all() for a in (u,vol,cur)) and np.all(np.diff(u)>0),"prefix clock")
 req(max(np.diff(u))<=30.5 and u[-1]<=900.5,"cadence")
 req(.95<=np.median(cur)<=1.05 and cur.min()>=.9 and cur.max()<=1.1,"prefix current")
 grid=np.arange(0,901,30);idx=[int(np.argmin(abs(u-k))) for k in grid]
 req(len(set(idx))==len(grid) and max(abs(u[k]-a) for k,a in zip(idx,grid))<=.5,"anchor")
 vv=vol[np.array(idx)[::5]]
 return list(map(float,-np.diff(vv)))
def groups(steps):
 g=[];gg=[];rw=False
 for j,s in enumerate(steps):
  if str(s["comment"])=="discharge (random walk)":rw=True
  if str(s["comment"])=="reference discharge":
   if rw and g:gg.append(g);g=[]
   rw=False;g.append((j,s))
 if g:gg.append(g)
 return gg
def reference(s):
 req(str(s["type"])=="D","type")
 t,v,i=[np.asarray(s[k],float).ravel() for k in ("relativeTime","voltage","current")]
 d=prefix(t,v,i)
 req(all(np.isfinite(a).all() for a in (t,v,i)) and np.all(np.diff(t)>=0) and t[-1]>t[0],"target clock")
 req(i.min()>=.9 and i.max()<=1.1 and 3.9<=v[0]<=4.3 and 3.15<=v[-1]<=3.25,"target protocol")
 q=float(np.trapezoid(i,t)/3600)
 req(abs(q-math.fsum((b-a)*(c+d)/7200 for a,b,c,d in zip(t,t[1:],i,i[1:])))<1e-10,"integral")
 return d,q
def metrics(rows,k,total):
 e=[r[k]-r["q"] for r in rows if r.get(k) is not None]
 return {"n":len(e),"total":total,"coverage":len(e)/total,"rmse_ah":math.sqrt(math.fsum(x*x for x in e)/len(e)) if e else None,"within":sum(abs(x)<=.1 for x in e),"fraction":sum(abs(x)<=.1 for x in e)/total,"bias_ah":math.fsum(e)/len(e) if e else None,"max_abs_ah":max(map(abs,e)) if e else None}
def controls():
 t=np.arange(0,901,10.);v=4.2-t*.0002;i=np.ones(len(t));d=prefix(t,v,i)
 req(np.allclose(d,prefix(t[::3],v[::3],i[::3])),"cadence")
 req(np.allclose(d,[.03]*6),"known drops")
 req(abs(pred(V4[0],V4)-V4[3])<1e-12 and abs(pred(LIN[0],LIN)-LIN[3])<1e-12,"centering")
 req(np.allclose(shape([.03]*6),[1/.03,1,1]),"shape")
 try:shape([.03,.03,.03,0,0,0])
 except ValueError:pass
 else:raise AssertionError("zero slope")
 req(metrics([{"q":1,"v4":1}],"v4",2)["fraction"]==.5,"denominator")
 print("6 controls passed",flush=True)
def main(out):
 controls();rows=[];bad=[];inv={}
 with tempfile.TemporaryDirectory() as td:
  p=pathlib.Path(td)/NAME;h=hashlib.sha256();m=hashlib.md5();size=0
  url="https://zenodo.org/records/15277374/files/"+urllib.parse.quote(NAME)+"?download=1"
  with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"GKA-RW1-V5/1.0"}),timeout=120) as r,p.open("xb") as f:
   while True:
    b=r.read(1024*1024)
    if not b:break
    h.update(b);m.update(b);size+=len(b);f.write(b)
  req(h.hexdigest()==SHA and m.hexdigest()==MD5 and size==446404182,"source identity")
  with zipfile.ZipFile(p) as z:
   req(z.testzip() is None,"CRC")
   names=[n for n in z.namelist() if n.endswith(".mat")]
   req(len(names)==4 and {pathlib.PurePosixPath(n).stem for n in names}=={"RW9","RW10","RW11","RW12"},"population")
   for n in sorted(names):
    c=pathlib.PurePosixPath(n).stem;b=z.read(n);steps=loadmat(io.BytesIO(b),simplify_cells=True)["data"]["step"];gg=groups(steps)
    req(sum(len(g) for g in gg)==sum(str(s["comment"])=="reference discharge" for s in steps),"tag accounting")
    inv[c]={"groups":len(gg),"mat_sha256":hashlib.sha256(b).hexdigest()}
    for k,g in enumerate(gg):
     j,s=g[0];ident={"cell":c,"checkpoint":k,"step":j}
     try:d,q=reference(s)
     except ValueError as e:bad.append(ident|{"reason":str(e)});continue
     p4=pred(d,V4);p5=None;reason=None
     try:p5=(pred(d,LIN)+pred(shape(d),INV))/2
     except ValueError as e:reason=str(e)
     rows.append(ident|{"d":d,"q":q,"v4":p4,"v5":p5,"v5_rejection":reason})
    del b,steps,gg,s,g;gc.collect()
 total=sum(x["groups"] for x in inv.values())
 req(total==156 and len(rows)==154 and len(bad)==2,"Windows population replay")
 metrics_all={k:metrics(rows,k,total) for k in ("v4","v5")}
 req(metrics_all["v4"]["within"]==87 and abs(metrics_all["v4"]["rmse_ah"]-0.10710807257425248)<1e-12,"Windows V4 baseline replay")
 per={c:{k:metrics([r for r in rows if r["cell"]==c],k,x["groups"]) for k in ("v4","v5")} for c,x in inv.items()}
 a=metrics_all["v5"];gate={"coverage":a["coverage"]>=.9,"rmse":a["rmse_ah"] is not None and a["rmse_ah"]<=.1,"tolerance":a["fraction"]>=.9,"per_cell":all(x["v5"]["rmse_ah"] is not None and x["v5"]["rmse_ah"]<=.15 for x in per.values())}
 report={"status":"EXPLORATORY_V5_GATE_PASS" if all(gate.values()) else "EXPLORATORY_V5_GATE_NOT_MET","source_sha256":SHA,"v4_model_receipt_sha":V4_SHA,"v5_model_receipt_sha":V5_SHA,"coefficients":{"v4":V4,"linear":LIN,"inverse":INV,"weights":[.5,.5]},"inventory":inv,"metrics":metrics_all,"per_cell":per,"gate":gate,"rows":rows,"rejected":bad,"limits":["V4 Windows aggregate known; V5 fixed before RW1 row-level analysis. Not a pristine blind test or independent laboratory.","Same 15-minute duration; V5 trained on 355 previous eligible records across five groups. No refitting here.","Retrospective full target quality control. No AGV, 5-minute or production safety claim."]}
 p=pathlib.Path(out);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("x") as f:json.dump(report,f,indent=2,allow_nan=False);f.write("\n")
 print(json.dumps({k:v for k,v in report.items() if k not in ("rows","rejected")}|{"report_sha256":hashlib.sha256(p.read_bytes()).hexdigest()}),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",default="evidence/GKA_NASA_RW1_V5_SHAPE_EXTERNAL_20261125.json");a=p.parse_args()
 if a.self_test:controls()
 else:main(a.output)
