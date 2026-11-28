"""Locked, index-held-out measurement baseline and synthetic loss stress; not a field qualification."""
import hashlib,json,pathlib,urllib.request
import numpy as np
from scipy.io import loadmat
from common_loss import fit,predict
from field_gate import ROOT,screen
PINS={"dataset_amb.mat":"e4619812a5b6c1331332248f052cb09938f9a43ccac8bcc512796c6e906da7e0","dataset_elec.mat":"c04ed3fcc0e338703e87d387b1ce6ef51da1848e77b4d491e62afe08934ce494"}
def main():
    d={}
    for name,h in PINS.items():
        with urllib.request.urlopen(ROOT+name,timeout=90) as r:b=r.read()
        assert hashlib.sha256(b).hexdigest()==h
        p=pathlib.Path(name);p.write_bytes(b)
        d.update({k:np.asarray(v).ravel().astype(float) for k,v in loadmat(p).items() if not k.startswith("__")})
    g,v,w,i,j,y=[d[k] for k in ("irr","vdc1","vdc2","idc1","idc2","f_nv")]
    assert len(g)==1373798 and all(len(x)==len(g) for x in (v,w,i,j,y))
    good=np.logical_and.reduce([np.isfinite(x)&(x>=0) for x in (v,w,i,j)])
    p=np.where(good,v*i,np.nan);q=np.where(good,w*j,np.nan)
    cut=len(g)//2; train=(np.arange(len(g))<cut)&(y==0);test=(np.arange(len(g))>=cut)&(y==0)
    b=fit(g[train],p[train],q[train]);assert b
    g,p,q,v,w,i,j=[a[test] for a in (g,p,q,v,w,i,j)]
    raw=predict(b,g,p,q);supported=raw!="UNAVAILABLE";assert supported.any()
    rows=[]
    for factor in (1.,.8,.6,.4,0.):
        z=predict(b,g,p*factor,q*factor)
        a,ok=screen(v,w,i*factor,j*factor,g)
        assert np.array_equal(supported,z!="UNAVAILABLE")
        rows.append({"power_multiplier":factor,"supported_rows":int(supported.sum()),"common_low":int(np.sum(z=="COMMON_LOW")),"common_rate":float(np.mean(z[supported]=="COMMON_LOW")),"asymmetry_valid":int(np.sum(ok&supported)),"asymmetry_alarms":int(np.sum(ok&supported&(a>.05)))})
    report={"source_sha256":PINS,"reference_cut_index":cut,"training_normal_rows":int(train.sum()),"heldout_normal_rows":int(test.sum()),"supported":int(supported.sum()),"unavailable":int((~supported).sum()),"bin_reference":b,"results":rows,"limits":"Index split only; timestamps and independent devices not established. Same-site normal reference, measured irradiance stratification only; temperature, clipping, sensor drift, operating mode not corrected. Multiplicative loss is synthetic, not independently measured concurrent faults. Threshold 25 percent selected in advance; report false alarms and coverage, do not deploy automatically."}
    pathlib.Path("EPS_COMMON_LOSS.json").write_text(json.dumps(report,indent=2,allow_nan=False));print(json.dumps(report,indent=2))
if __name__=="__main__":main()
