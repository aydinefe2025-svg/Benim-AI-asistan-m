"""Causal persistence screen on pinned independent physical measurements."""
import hashlib,json,pathlib,urllib.request
import numpy as np
from scipy.io import loadmat
from field_gate import screen,ROOT
PINS={"dataset_amb.mat":"e4619812a5b6c1331332248f052cb09938f9a43ccac8bcc512796c6e906da7e0","dataset_elec.mat":"c04ed3fcc0e338703e87d387b1ce6ef51da1848e77b4d491e62afe08934ce494"}
def persist(mask,n):
    idx=np.arange(len(mask)); last=np.maximum.accumulate(np.where(~mask,idx,-1))
    return mask & (idx-last>=n)
def tests():
    np.testing.assert_array_equal(persist(np.array([True,True,False,True,True,True]),3),[False,False,False,False,False,True])
    np.testing.assert_array_equal(persist(np.array([False,True,True]),1),[False,True,True])
    np.testing.assert_array_equal(persist(np.array([True,False,True]),2),[False,False,False])
def evaluate(labels,valid,score,n):
    alarms=persist(valid & (score>.05),n)
    out={}
    for k in range(5):
        m=(labels==k)&valid
        out[str(k)]={"eligible":int(m.sum()),"alarm":int((alarms&m).sum()),"rate":float((alarms&m).sum()/m.sum()) if m.any() else None}
    # Events: contiguous label runs, count only runs with at least n consecutive eligible observations.
    starts=np.flatnonzero(np.r_[True,labels[1:]!=labels[:-1]]); ends=np.r_[starts[1:],len(labels)]
    events={}
    for k in range(5):
        e=[(a,b) for a,b in zip(starts,ends) if labels[a]==k and persist(valid[a:b],n).any()]
        hits=[int(np.flatnonzero(alarms[a:b])[0]) for a,b in e if alarms[a:b].any()]
        events[str(k)]={"eligible_runs":len(e),"alarmed_runs":len(hits),"median_first_alarm_offset_rows":float(np.median(hits)) if hits else None}
    return {"rows":out,"runs":events}
def main():
    tests(); d={}
    for name,h in PINS.items():
        with urllib.request.urlopen(ROOT+name,timeout=90) as r:b=r.read()
        assert hashlib.sha256(b).hexdigest()==h
        p=pathlib.Path(name);p.write_bytes(b);d.update({k:np.asarray(v).ravel().astype(float) for k,v in loadmat(p).items() if not k.startswith("__")})
    l=d["f_nv"]; s,v=screen(*(d[k] for k in ("vdc1","vdc2","idc1","idc2","irr")))
    assert len(l)==1373798 and int(v.sum())==497407
    # Chronological index blocks, not asserted to represent calendar days. Reset at each block boundary.
    blocks=np.array_split(np.arange(len(l)),8)
    receipt={"source_sha256":PINS,"threshold":.05,"overall":{str(n):evaluate(l,v,s,n) for n in (1,5,30,60)},"index_blocks":[{"start":int(b[0]),"end_exclusive":int(b[-1]+1),"results":{str(n):evaluate(l[b],v[b],s[b],n) for n in (1,5,30,60)}} for b in blocks],"limits":"Prespecified row persistence, no inferred timestamps or independent devices. Invalid rows reset alarm. Runs are label segments, not verified physical events. Alarm may carry over from preceding eligible label; no use of labels in detection. Descriptive sensitivity on same plant, not independent product qualification."}
    pathlib.Path("EPS_PERSISTENCE.json").write_text(json.dumps(receipt,indent=2,allow_nan=False));print(json.dumps({"overall":receipt["overall"],"block_30_rates":[x["results"]["30"]["rows"] for x in receipt["index_blocks"]]},indent=2))
if __name__=="__main__":main()
