"""XJTU independent laboratory transfer; fixed NASA coefficients, no XJTU fit."""
import argparse, collections, hashlib, io, json, math, pathlib, re, time, urllib.request, zipfile
import numpy as np
from scipy.io import loadmat
from gka_nasa_rw1_v5_shape_external import V4, pred
URL="https://zenodo.org/records/10963339/files/Battery%20Dataset.zip?download=1"
SIZE=2438769934
KNOWN_SHA="4c68a1b0aa80502c438258dff7137fe788bc355aedbe977fbf3420d4f2247f3f"
M5=([0.11291355599214145,0.036559921414538316],[0.03983734602650468,0.010325110292285127],[0.09558782400771206,-0.412854926168426],1.5346322566470205)
M5_SHA="6254186e81026beebd6735295f10dbfb6af7375ba25ddeb6d467d97cf8ac1261"
def require(ok,msg):
    if not ok:raise ValueError(msg)
def get(a,b):
    for attempt in range(3):
        try:
            req=urllib.request.Request(URL,headers={"Range":f"bytes={a}-{b}","User-Agent":"GKA-XJTU-transfer/1.0","Accept-Encoding":"identity"})
            with urllib.request.urlopen(req,timeout=90) as r:
                require(r.status==206,"range status")
                m=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)",r.headers["Content-Range"] or "")
                require(m and tuple(map(int,m.groups()))==(a,b,SIZE),"range identity")
                data=r.read(b-a+2)
                require(len(data)==b-a+1,"range length")
                return data
        except (OSError,ValueError):
            if attempt==2:raise
            time.sleep(2**attempt)
class Remote(io.RawIOBase):
    def __init__(self):self.pos=0
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,o,w=0):
        self.pos=o if w==0 else self.pos+o if w==1 else SIZE+o
        return self.pos
    def read(self,n=-1):
        n=SIZE-self.pos if n<0 else min(n,SIZE-self.pos)
        if n<=0:return b""
        parts=[]
        while n:
            k=min(n,16*1024*1024)
            parts.append(get(self.pos,self.pos+k-1));self.pos+=k;n-=k
        return b"".join(parts)
def label(s):
    s=" ".join(str(s).lower().split())
    if "test capacity" not in s:return "not_reference"
    if re.search(r"0\.2\s*c\s+discharge",s):return "initial_0p4A"
    if re.search(r"0\.5\s*c\s+discharge",s):return "reference_1A"
    return "unclassified_reference"
def runs(mask):
    idx=np.flatnonzero(np.diff(np.r_[False,mask,False]))
    return list(zip(idx[::2],idx[1::2]))
def target(t,v,i):
    t,v,i=[np.asarray(a,float).ravel() for a in (t,v,i)]
    require(len(t)==len(v)==len(i) and len(t)>2 and all(np.isfinite(a).all() for a in (t,v,i)),"invalid arrays")
    candidates=[]
    for sign in (-1,1):
        for a,b in runs(sign*i>.1):
            if b-a>1 and v[a]>=3.9 and v[a]<=4.3 and np.min(v[a:b])<=3.2:
                candidates.append((a,b,sign))
    require(len(candidates)==1,"unique full discharge run")
    a,b,sign=candidates[0]
    k=a+int(np.flatnonzero(v[a:b]<=3.2)[0])
    require(k>a,"cutoff at first point")
    tt=t[a:k+1]-t[a];vv=v[a:k+1];ii=sign*i[a:k+1]
    require(np.all(np.diff(tt)>0) and max(np.diff(tt))<=30.5,"target clock")
    require(ii.min()>=.9 and ii.max()<=1.1 and .95<=np.median(ii)<=1.05,"1A protocol")
    f=(vv[-2]-3.2)/(vv[-2]-vv[-1])
    require(0<f<=1,"cutoff interpolation")
    tcut=tt[-2]+f*(tt[-1]-tt[-2]);icut=ii[-2]+f*(ii[-1]-ii[-2])
    ti=np.r_[tt[:-1],tcut];ci=np.r_[ii[:-1],icut]
    q=float(np.trapezoid(ci,ti)/3600)
    q2=math.fsum((y-x)*(u+w)/7200 for x,y,u,w in zip(ti,ti[1:],ci,ci[1:]))
    require(abs(q-q2)<1e-10,"integral replay")
    return tt,vv,ii,q,{"start_index":int(a),"cutoff_index":int(k),"sign":sign,"start_voltage":float(vv[0]),"cutoff_s":float(tcut),"max_gap_s":float(max(np.diff(tt))),"integration_difference_ah":abs(q-q2)}
def features(t,v,i,w):
    h=np.flatnonzero(t>=w-.5)
    require(len(h)>0,"short prefix")
    j=int(h[0]);t,v,i=t[:j+1],v[:j+1],i[:j+1]
    require(t[-1]<=w+.5 and np.all(np.diff(t)>0) and max(np.diff(t))<=30.5,"prefix clock")
    grid=np.arange(0,w+1,30);idx=[int(np.argmin(abs(t-x))) for x in grid]
    require(len(set(idx))==len(grid) and max(abs(t[j]-x) for j,x in zip(idx,grid))<=.5,"prefix grid")
    return list(map(float,-np.diff(v[np.array(idx)[::5]])))
def met(rows,key,total):
    e=[r[key]-r["q"] for r in rows if r.get(key) is not None]
    return {"n":len(e),"total":total,"coverage":len(e)/total if total else None,"within":sum(abs(x)<=.1 for x in e),"fraction":sum(abs(x)<=.1 for x in e)/total if total else None,"rmse_ah":math.sqrt(math.fsum(x*x for x in e)/len(e)) if e else None,"bias_ah":math.fsum(e)/len(e) if e else None}
def controls():
    t=np.arange(0,3601,dtype=float);v=4.2-t/3600;i=-np.ones(len(t))
    tt,vv,ii,q,diag=target(t,v,i)
    require(abs(q-1)<1e-12 and diag["sign"]==-1,"constant capacity")
    require(abs(target(t,v,-i)[3]-1)<1e-12,"opposite sign")
    require(np.allclose(features(tt,vv,ii,300),[150/3600]*2),"five minute anchors")
    require(np.allclose(features(tt,vv,ii,900),[150/3600]*6),"fifteen minute anchors")
    t2=np.r_[0.,1.,2.,3.];v2=np.array([4.0,3.7,3.3,3.1])
    require(abs(target(t2,v2,-np.ones(4))[3]-2.5/3600)<1e-12,"cutoff interpolation")
    require(label("1C charge and 0.5C discharge [test capacity]")=="reference_1A" and label("0.5C charge and 0.2C discharge [test capacity]")=="initial_0p4A","protocol label")
    require(met([{"q":1,"p":1}],"p",2)["fraction"]==.5,"abstention")
    require(abs(pred(M5[0],M5)-M5[3])<1e-12,"model center")
    print("8 synthetic controls passed",flush=True)
def evaluate(cell,out):
    name=f"Battery Dataset/Batch-6/Sim_satellite_battery-{cell}.mat"
    with zipfile.ZipFile(Remote()) as z:
        inf=z.getinfo(name);raw=z.read(name)
        require(len(raw)==inf.file_size,"member size")
        import zlib
        require(zlib.crc32(raw)==inf.CRC,"member CRC")
    h=hashlib.sha256(raw).hexdigest()
    if cell==1:require(h==KNOWN_SHA and inf.CRC==0x9bd2af73,"Windows byte replay")
    d=loadmat(io.BytesIO(raw),simplify_cells=True)["data"]
    tags=collections.Counter(str(s["description"]) for s in d)
    rows=[];rejected=[];prev=None;n=0
    for j,s in enumerate(d):
        tag=label(s["description"])
        if tag in ("not_reference","initial_0p4A"):continue
        n+=1
        ident={"cell":cell,"cycle":j,"reference":n-1,"description":str(s["description"])}
        if tag!="reference_1A":
            rejected.append(ident|{"reason":"unclassified reference"});continue
        try:
            t,v,i,q,diag=target(np.asarray(s["relative_time_min"])*60,s["voltage_V"],s["current_A"])
        except ValueError as e:
            rejected.append(ident|{"reason":str(e)});continue
        r=ident|{"q":q,"diagnostics":diag,"v4":None,"m5":None,"adaptive5":None,"last_actual":None}
        try:
            x=features(t,v,i,300)
            r.update({"d5":x,"m5":pred(x,M5)})
            if prev is not None:
                require(prev["cycle"]<j,"chronology")
                r.update({"previous_cycle":prev["cycle"],"previous_q":prev["q"],"last_actual":prev["q"],"adaptive5":prev["q"]+r["m5"]-prev["m5"]})
            prev=r
        except ValueError as e:r["m5_rejection"]=str(e)
        try:
            x=features(t,v,i,900);r.update({"d15":x,"v4":pred(x,V4)})
        except ValueError as e:r["v4_rejection"]=str(e)
        rows.append(r)
    require(n>0 and len(rows)+len(rejected)==n,"reference accounting")
    conditional=[r for r in rows if r["reference"]>0]
    metrics={"v4":met(rows,"v4",n),"m5":met(rows,"m5",n),"adaptive5":met(conditional,"adaptive5",n-1),"last_actual":met([r for r in conditional if r["adaptive5"] is not None],"last_actual",n-1)}
    report={"cell":cell,"source_member":name,"member_bytes":len(raw),"member_crc32":f"{inf.CRC:08x}","member_sha256":h,"cycles":len(d),"labels":dict(tags),"reference_total":n,"metrics":metrics,"rows":rows,"rejected":rejected,"fixed_models":{"V4":V4,"M5":M5,"M5_receipt_sha256":M5_SHA},"limits":["ZIP selected member CRC verified; full archive publisher MD5 not verified.","XJTU chemistry/charge protocol differs; target is truncated 3.2 V capacity, not publisher full 2.5 V capacity.","Retrospective selection of full reference discharge; no claim of real-time identification or calibrated hardware safety.","Prior completed capacity required for conditional5; first reference excluded only for conditional metrics.","Source descriptions define 1A candidates; unknown reference descriptions retained as abstentions."]}
    p=pathlib.Path(out);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("x") as f:json.dump(report,f,indent=2,allow_nan=False);f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("rows","rejected")}|{"report_sha256":hashlib.sha256(p.read_bytes()).hexdigest()}),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--cell",type=int,choices=range(1,9));p.add_argument("--output");a=p.parse_args()
    controls()
    if not a.self_test:
        require(a.cell is not None and a.output,"cell/output required");evaluate(a.cell,a.output)
