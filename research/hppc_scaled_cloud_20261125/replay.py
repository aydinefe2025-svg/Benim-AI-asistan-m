"""Public-source replay of the 24 low-voltage Samsung 50E traces.
No physical certification; no changes to source measurements.
"""
import csv, datetime, hashlib, itertools, json, math, pathlib, statistics, sys
import numpy as np

ROOT=pathlib.Path(sys.argv[1])
OUT=pathlib.Path(sys.argv[2])
TAUS=(2.562132249982305,30.)
FROZEN=np.array([.026383737250879113,1.1878550863477837,.002636255446005764,.015645941199294383])
LOW=3.3645454999999997

def records(p, prefix=False):
    rows=[]; markers=[]; seen=set()
    with p.open(encoding="utf-8-sig",newline="") as f:
        rd=csv.reader(f); hdr=next(rd)
        assert hdr[0]=="Time" and hdr[-1]=="hp_pulse",p
        for r in rd:
            assert len(r)==11,p
            if r[2] and r[9]:
                t=datetime.datetime.strptime(r[0][:-1],"%d.%m.%Y %H:%M:%S.%f")
                if prefix and t not in seen and len(seen)==10: break
                seen.add(t);rows.append((t,float(r[2]),float(r[9])))
            elif r[-1]:markers.append(r[-1])
            else:raise ValueError("invalid row")
    if not prefix:assert "88" in markers and "99" in markers,p
    t=np.array([(r[0]-rows[0][0]).total_seconds() for r in rows]);a=np.array([r[1:] for r in rows])
    assert np.isfinite(a).all() and np.all(np.diff(t)>=0) and np.max(np.diff(t))<.01,p
    u,ix,ct=np.unique(t,return_index=True,return_counts=True)
    a=np.add.reduceat(a,ix,axis=0)/ct[:,None]
    assert len(a)>=10
    bi,bv=a[:10].mean(axis=0)
    if prefix:return float(bv)
    bins=np.floor((u+1e-9)/.02).astype(int);_,ix,ct=np.unique(bins,return_index=True,return_counts=True)
    assert np.all(np.diff(bins[ix])==1)
    t=(np.add.reduceat(u,ix)/ct)[:-1];a=(np.add.reduceat(a,ix,axis=0)/ct[:,None])[:-1]
    return t,a[:,0]-bi,a[:,1]-bv,float(bv),len(rows)

def integral(t,i):
    return np.r_[0.,np.cumsum((i[1:]+i[:-1])*.5*np.diff(t))/3600]

def rc(t,i,tau):
    y=np.zeros_like(i)
    for k,dt in enumerate(np.diff(t),1):
        a=math.exp(-dt/tau);y[k]=a*y[k-1]+(1-a)*(i[k-1]+i[k])*.5
    return y

def design(t,i):
    q=integral(t,i);dq=integral(t,np.maximum(-i,0));states=[rc(t,i,a) for a in TAUS]
    return np.column_stack([i,q,*states]),np.column_stack([np.maximum(i,0),np.minimum(i,0),q,*states,-dq*dq])

def solve(X,y,scaled):
    if not scaled:
        G=X.T@X;h=X.T@y;yy=float(y@y);best=yy;out=np.zeros(X.shape[1])
        for k in range(1,X.shape[1]+1):
            for ix in itertools.combinations(range(X.shape[1]),k):
                ix=list(ix);v=np.linalg.lstsq(G[np.ix_(ix,ix)],h[ix],rcond=1e-12)[0]
                if np.any(v<-1e-12):continue
                b=np.zeros(X.shape[1]);b[ix]=np.maximum(v,0)
                loss=max(0,float(b@G@b-2*b@h+yy))
                if loss<best:best=loss;out=b
        return out,True,{}
    norms=np.linalg.norm(X,axis=0);valid=np.flatnonzero(norms>0)
    A=X[:,valid]/norms[valid];s=np.linalg.svd(A,compute_uv=False)
    rank=int(np.sum(s>s[0]*1e-12));cond=float(s[0]/s[-1]) if s[-1]>0 else None
    diag={"rank":rank,"columns":X.shape[1],"condition_scaled":cond}
    if rank!=X.shape[1] or cond is None or cond>1e6:return np.zeros(X.shape[1]),False,diag
    best=float(y@y);z=np.zeros(len(valid))
    for k in range(1,len(valid)+1):
        for ix in itertools.combinations(range(len(valid)),k):
            v=np.linalg.lstsq(A[:,ix],y,rcond=1e-12)[0]
            if np.any(v<-1e-12):continue
            v=np.maximum(v,0);e=A[:,ix]@v-y;loss=float(e@e)
            if loss<best:best=loss;z[:]=0;z[list(ix)]=v
    out=np.zeros(X.shape[1]);out[valid]=z/norms[valid]
    assert np.isfinite(out).all()
    return out,True,diag

def gate(t,i,v,scaled):
    X,Z=design(t,i);start=t[np.flatnonzero(i<-3)[0]]
    pre=t<start+1;val=(t>=start+1)&(t<start+2);fit=t<start+2;test=~fit
    assert pre.sum()>1000 and val.sum()>=45 and test.sum()>1000
    base=X@FROZEN; scores={"frozen":float(np.mean(abs(base[val]-v[val])))}
    ds={};designs={"local_2RC":X,"direction_curvature":Z}
    for name,F in designs.items():
        b,ok,diag=solve(F[pre],v[pre],scaled);ds[name]=diag
        if ok:scores[name]=float(np.mean(abs(F[val]@b-v[val])))
    choice=min(scores,key=scores.get);params=FROZEN;pred=base
    if choice!="frozen" and scores[choice]<.9*scores["frozen"]:
        F=designs[choice];b,ok,diag=solve(F[fit],v[fit],scaled);ds["refit"]=diag
        if ok:params=b;pred=F@b
        else:choice="frozen"
    else:choice="frozen"
    e=1000*(pred[test]-v[test])
    return {"choice":choice,"MAE_mV":float(np.mean(abs(e))),"RMSE_mV":float(np.sqrt(np.mean(e*e))),"max_mV":float(np.max(abs(e))),"params":params.tolist(),"holdout_points":int(test.sum()),"cut_s":float(start+2),"diagnostics":ds,"scores_V":scores}

def main():
    files=sorted(ROOT.glob("HPPCs/Batch*/*.csv"))
    assert len(files)==254 and len({p.parent.name for p in files})==32
    training=[p for p in files if p.parent.name=="Batch19"];assert len(training)==8
    lo=min(records(p,True) for p in training);assert abs(lo-LOW)<1e-10
    selected=[p for p in files if p not in training and records(p,True)<lo]
    assert len(selected)==24
    results=[]
    for p in selected:
        t,i,v,bv,n=records(p);assert bv<lo
        old=gate(t,i,v,False);new=gate(t,i,v,True)
        assert old["holdout_points"]==new["holdout_points"]
        row={"member":str(p.relative_to(ROOT)),"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"initial_V":bv,"numeric_rows":n,"legacy":old,"scaled":new}
        results.append(row)
        print(json.dumps({"member":row["member"],"old":old["MAE_mV"],"new":new["MAE_mV"],"choice":new["choice"]}),flush=True)
    a=statistics.mean(x["legacy"]["MAE_mV"] for x in results);b=statistics.mean(x["scaled"]["MAE_mV"] for x in results)
    # The previous Windows aggregate is an independent reproduction target, not a fit target.
    assert abs(a-3.9206089537565467)<1e-5,(a,"legacy replay drift")
    summary={"files":24,"legacy_mean_mV":a,"scaled_mean_mV":b,"improved":sum(x["scaled"]["MAE_mV"]<x["legacy"]["MAE_mV"]-1e-8 for x in results),"worsened":sum(x["scaled"]["MAE_mV"]>x["legacy"]["MAE_mV"]+1e-8 for x in results),"legacy_worst_mV":max(x["legacy"]["MAE_mV"] for x in results),"scaled_worst_mV":max(x["scaled"]["MAE_mV"] for x in results)}
    report={"goal_key":"battery-20261125-hppc-scaled-cloud-replay-v1","archive_sha256":"36a8bd0904a27fd90e44820c5cf938c8e7ed3e01acb6d2232c759b9f07e811cf","scope":"same previously observed 24 low-voltage source files; no independent cell or temperature certification","summary":summary,"results":results}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"result.json").write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    print("SUMMARY",json.dumps(summary),flush=True)

if __name__=="__main__":main()
