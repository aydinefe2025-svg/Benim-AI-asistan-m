"""Read-only operational replay. Historical physical measurements, no actuator interface."""
import hashlib,json,math,pathlib,urllib.request
import numpy as np
from scipy.io import loadmat
from field_gate import ROOT,screen
from field_persistence import PINS,persist
class Monitor:
    def __init__(self,streak=0,position=0,n=5):
        self.streak=streak;self.position=position;self.n=n
    def step(self,v1,v2,i1,i2,g):
        ok=all(math.isfinite(x) and x>=0 for x in (v1,v2,i1,i2,g)) and g>=200
        p,q=v1*i1,v2*i2
        ok=ok and math.isfinite(p+q) and p+q>0
        score=abs(p-q)/(p+q) if ok else None
        self.streak=self.streak+1 if ok and score>.05 else 0
        self.position+=1
        return (score,"ALARM" if self.streak>=self.n else "WATCH" if self.streak else "NORMAL" if ok else "UNAVAILABLE")
    def checkpoint(self):
        return dict(streak=self.streak,position=self.position,n=self.n)
def tests():
    m=Monitor(); bad=(100,100,2,0,800); good=(100,100,2,2,800)
    assert [m.step(*bad)[1] for _ in range(5)]==["WATCH"]*4+["ALARM"]
    assert m.step(*good)[1]=="NORMAL"
    for _ in range(4):m.step(*bad)
    m=Monitor(**json.loads(json.dumps(m.checkpoint())))
    assert m.step(*bad)[1]=="ALARM"
    assert m.step(100,100,2,0,float("nan"))[1]=="UNAVAILABLE"
    assert m.step(*bad)[1]=="WATCH"
    assert m.step(100,100,-1,2,800)[1]=="UNAVAILABLE"
    print("5 operational invariants passed")
def main():
    tests();d={}
    for name,h in PINS.items():
        with urllib.request.urlopen(ROOT+name,timeout=90) as r:b=r.read()
        assert hashlib.sha256(b).hexdigest()==h
        p=pathlib.Path(name);p.write_bytes(b);d.update({k:np.asarray(v).ravel().astype(float) for k,v in loadmat(p).items() if not k.startswith("__")})
    l=d["f_nv"]; x=[d[k] for k in ("vdc1","vdc2","idc1","idc2","irr")]
    score,valid=screen(*x); expected=persist(valid&(score>.05),5)
    m=Monitor();alarm=np.zeros(len(l),bool);eligible=np.zeros(len(l),bool);counts={k:0 for k in ("NORMAL","WATCH","ALARM","UNAVAILABLE")}
    for start in range(0,len(l),10000):
        for j,values in enumerate(zip(*(a[start:start+10000] for a in x)),start):
            s,status=m.step(*values);alarm[j]=status=="ALARM";eligible[j]=s is not None;counts[status]+=1
        m=Monitor(**json.loads(json.dumps(m.checkpoint())))
    assert m.position==len(l)==1373798
    assert np.array_equal(alarm,expected) and np.array_equal(eligible,valid)
    windows=[]
    for k in range(5):
        idx=np.flatnonzero(persist(valid&(l==k),120));assert len(idx)>0
        end=int(idx[0])+1;start=end-120
        windows.append({"label":k,"start":start,"rows":[[float(a[j]) for a in x] for j in range(start,end)]})
    receipt={"mode":"HISTORICAL_REPLAY_ONLY","rows":len(l),"eligible":int(valid.sum()),"state_counts":counts,"checkpoint_restarts":math.ceil(len(l)/10000),"stream_batch_mismatches":int(np.count_nonzero(alarm!=expected)),"source_sha256":PINS,"preview_windows":windows,"limits":"Selected first eligible 120-row label windows for demonstration, not representative or independent evaluation. Hardware not connected. Alarm is imbalance, not fault-type diagnosis."}
    pathlib.Path("EPS_REPLAY.json").write_text(json.dumps(receipt,allow_nan=False))
    template=pathlib.Path("replay_template.html").read_text(encoding="utf-8")
    pathlib.Path("CANO_EPS_REPLAY.html").write_text(template.replace("__REPLAY_DATA__",json.dumps(receipt,allow_nan=False)),encoding="utf-8")
    print(json.dumps({k:v for k,v in receipt.items() if k!="preview_windows"},indent=2))
if __name__=="__main__":main()
