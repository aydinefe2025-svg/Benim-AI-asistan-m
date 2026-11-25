"""Independent field string-power asymmetry screen; not a V5 module-MPP calibration."""
import hashlib,json,pathlib,urllib.request
import numpy as np
from scipy.io import loadmat
PIN="e9ed8ad8072dcb3ffc643b0f3604219798708551"
ROOT="https://raw.githubusercontent.com/clayton-h-costa/pv_fault_dataset/"+PIN+"/"
def screen(v1,v2,i1,i2,g):
    p1,p2=v1*i1,v2*i2
    valid=np.isfinite(v1)&np.isfinite(v2)&np.isfinite(i1)&np.isfinite(i2)&np.isfinite(g)&(v1>=0)&(v2>=0)&(i1>=0)&(i2>=0)&(g>=200)&(p1+p2>0)
    score=np.full(g.shape,np.nan,dtype=float)
    np.divide(abs(p1-p2),p1+p2,out=score,where=valid)
    return score,valid
def tests():
    a=np.array
    s,v=screen(a([100.,100.,100.,100.]),a([100.,100.,100.,100.]),a([2.,2.,0.,2.]),a([2.,0.,0.,2.]),a([800.,800.,800.,100.]))
    np.testing.assert_allclose(s[:2],[0.,1.]); assert v.tolist()==[True,True,False,False]
    _,v=screen(*map(a,([100.],[100.],[-1.],[2.],[800.])))
    assert not v[0]
    print("Two screen tests passed")
def main():
    tests()
    files={}
    data={}
    for name in ("dataset_amb.mat","dataset_elec.mat"):
        p=pathlib.Path(name)
        with urllib.request.urlopen(ROOT+name,timeout=90) as r: b=r.read()
        p.write_bytes(b); files[name]={"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
        data.update({k:np.asarray(v).ravel().astype(float) for k,v in loadmat(p).items() if not k.startswith("__")})
    labels=data["f_nv"]
    x=[data[k] for k in ("vdc1","vdc2","idc1","idc2","irr")]
    assert len({len(labels),len(data["pvt"]),*(len(v) for v in x)})==1
    assert set(np.unique(labels))=={0,1,2,3,4}
    score,valid=screen(*x)
    result={}
    for k in range(5):
        m=labels==k; z=score[m&valid]; assert z.size>0
        result[str(k)]={"raw_rows":int(m.sum()),"valid_rows":int(z.size),"median":float(np.median(z)),"p95":float(np.quantile(z,.95)),"fraction_above_threshold":{str(t):float((z>t).mean()) for t in (.05,.10,.20)}}
    receipt={"source_commit":PIN,"paper":"https://doi.org/10.3390/s20174688","files":files,"rows":len(labels),"valid_rows":int(valid.sum()),"labels":result,"thresholds":"Preselected descriptive fractions, not trained or certified; daylight >=200 W/m2, nonnegative V and I, positive summed string power. Serial observations are not independent; no timestamp-based or device-held-out claim. String operating power is not module sampled Pmax; cannot establish V5 physical qualification or original Sandia calibration."}
    pathlib.Path("EPS_FIELD_SCREEN.json").write_text(json.dumps(receipt,indent=2,allow_nan=False)); print(json.dumps(receipt,indent=2))
if __name__=="__main__": main()
