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


def stable_gate(t,i,v,legacy,cut):
    """Exploratory causal variants: no persistent squared-charge extrapolation.
    First cut-1 seconds after discharge onset used for fit, last second for selection.
    Legacy prediction always comes from its fixed original 2-second calibration.
    """
    X,Z=design(t,i);start=t[np.flatnonzero(i<-3)[0]]
    pre=t<start+cut-1;val=(t>=start+cut-1)&(t<start+cut);fit=t<start+cut;test=~fit
    assert val.sum()>=45 and test.sum()>1000
    assert cut>=2 and t[np.flatnonzero(i<-3)[-1]]>start+cut
    base=X@FROZEN
    legacy_design={"frozen":X,"local_2RC":X,"direction_curvature":Z}
    reference=legacy_design[legacy["choice"]]@np.array(legacy["params"])
    D=Z[:,:-1]
    dq=integral(t,np.maximum(-i,0))
    # A varying discharge resistance vanishes when the current returns to zero.
    J=np.column_stack([D,np.minimum(i,0)*dq])
    candidates={"local_2RC":X,"direction_only":D,"direction_charge_resistance":J}
    scores={"frozen":float(np.mean(abs(base[val]-v[val])))}
    for name,A in candidates.items():
        b,ok,_=solve(A[pre],v[pre],True)
        if ok:scores[name]=float(np.mean(abs(A[val]@b-v[val])))
    choice=min(scores,key=scores.get);pred=base;params=FROZEN
    if choice!="frozen" and scores[choice]<.9*scores["frozen"]:
        A=candidates[choice];b,ok,_=solve(A[fit],v[fit],True)
        if ok:pred=A@b;params=b
        else:choice="frozen"
    else:choice="frozen"
    def metrics(p,mask):
        e=1000*(p[mask]-v[mask])
        return {"MAE_mV":float(np.mean(abs(e))),"RMSE_mV":float(np.sqrt(np.mean(e*e))),"max_mV":float(np.max(abs(e))),"points":int(mask.sum())}
    # A causal, current-dependent prediction blend: no future measured voltage.
    # Keep the already validated legacy relaxation prediction exactly.
    w=np.clip((-i-3.)/1.,0.,1.)
    w=w*w*(3.-2.*w)
    blended=reference+w*(pred-reference)
    hard=np.where(i<-3,pred,reference)
    assert np.array_equal(blended[i>=-3],reference[i>=-3])
    assert np.all(np.isfinite(blended))
    assert np.all((w>=0)&(w<=1))
    phase={"hard":metrics(hard,test),"smooth":metrics(blended,test),
           "smooth_discharge":metrics(blended,test&(i<-3)),
           "smooth_rest":metrics(blended,test&(i>=-3)),
           "ramp_points":int(np.sum(test&(w>0)&(w<1))),
           "max_smooth_minus_hard_mV":float(1000*np.max(abs(blended[test]-hard[test])))}

    # Continuous polarization-memory candidates. Fix instantaneous negative
    # current resistance to the independent Batch19 calibration, and keep
    # extra discharge polarization in states that decay rather than vanish.
    if cut==5.:
        neg=np.minimum(i,0.);pos=np.maximum(i,0.)
        q=integral(t,i);dq=integral(t,-neg)
        fixed=FROZEN[0]*neg
        mats={}
        for fast in (.1,.5,1.):
            for slow in (2.562132249982305,10.,30.):
                mats[(fast,slow)]=np.column_stack([pos,q,rc(t,i,TAUS[0]),rc(t,i,TAUS[1]),rc(t,neg,fast),rc(t,neg*dq,slow)])
        scores_mem={}
        for key,A in mats.items():
            b,ok,_=solve(A[pre],v[pre]-fixed[pre],True)
            if ok:scores_mem[key]=float(np.mean(abs(fixed[val]+A[val]@b-v[val])))
        assert scores_mem
        key=min(scores_mem,key=scores_mem.get);A=mats[key]
        b,ok,diag=solve(A[fit],v[fit]-fixed[fit],True)
        assert ok
        memory=fixed+A@b
        # Causal diagnostic: prefix objective is blind to holdout voltage.
        phase["memory_open_loop"]={"fast_s":key[0],"slow_s":key[1],"params":b.tolist(),"validation_MAE_mV":1000*scores_mem[key],"rank":diag["rank"],"all":metrics(memory,test),"discharge":metrics(memory,test&(i<-3)),"rest":metrics(memory,test&(i>=-3))}
        phase["memory_open_loop"]["peak_at_blend_mV"]=float(1000*(memory[np.flatnonzero(test)[np.argmax(abs(blended[test]-v[test]))]]-v[np.flatnonzero(test)[np.argmax(abs(blended[test]-v[test]))]]))

    # Separate open-loop accuracy from a voltage-feedback predictor.
    # At k, only v[k-h] and earlier may be used; measured current through k
    # is available (conditional prediction, not unknown future current).
    if cut==5.:
        peak=int(np.flatnonzero(test)[np.argmax(abs(blended[test]-v[test]))])
        ix=np.arange(max(0,peak-8),min(len(t),peak+9))
        phase["peak"]={"index":peak,"t_s":float(t[peak]),"relative_V":float(v[peak]),"I_A":float(i[peak]),"signed_error_mV":float(1000*(blended[peak]-v[peak])),"window":[{"t_s":float(t[k]),"I_A":float(i[k]),"V":float(v[k]),"legacy_V":float(reference[k]),"candidate_V":float(pred[k]),"blend_V":float(blended[k])} for k in ix]}
        phase["open_loop_diagnostic"]={"stable":metrics(pred,test),"legacy":metrics(reference,test),"blend":metrics(blended,test)}
        # Exact last-observation residual correction, using a single
        # continuous base for the increment rather than a model switch.
        phase["conditional_feedback"]={}
        for h in (1,5,50):
            mask=test.copy();mask[:h]=False
            k=np.flatnonzero(mask);j=k-h
            assert np.all(j<k)
            pp={"persistence":v[j],"legacy_increment":v[j]+reference[k]-reference[j],"stable_increment":v[j]+pred[k]-pred[j],"blend_increment":v[j]+blended[k]-blended[j],"ohmic_increment":v[j]+FROZEN[0]*(i[k]-i[j])}
            dd={}
            for name,yhat in pp.items():
                err=1000*(yhat-v[k]);ae=abs(err);m=int(np.argmax(ae))
                dd[name]={"MAE_mV":float(ae.mean()),"RMSE_mV":float(np.sqrt(np.mean(err*err))),"max_mV":float(ae[m]),"peak_t_s":float(t[k[m]]),"peak_I_A":float(i[k[m]]),"points":len(k),"over_50mV":int(np.sum(ae>50))}
            phase["conditional_feedback"][str(h)]=dd

    assert abs(phase["smooth_rest"]["MAE_mV"]-metrics(reference,test&(i>=-3))["MAE_mV"])<1e-12
    return {"phase_guard":phase,"choice":choice,"scores_V":scores,"params":params.tolist(),"cut_s":float(start+cut),"legacy":metrics(reference,test),"candidate":metrics(pred,test),
            "legacy_remaining_discharge":metrics(reference,test&(i<-3)),"candidate_remaining_discharge":metrics(pred,test&(i<-3)),
            "legacy_rest":metrics(reference,test&(i>=-3)),"candidate_rest":metrics(pred,test&(i>=-3))}
def summarize_stable(results,key):
    a=[r[key] for r in results]
    out={}
    for label in ("","_remaining_discharge","_rest"):
        old=[r["legacy"+label]["MAE_mV"] for r in a];new=[r["candidate"+label]["MAE_mV"] for r in a]
        out[label or "all"]={"legacy_mean_mV":statistics.mean(old),"candidate_mean_mV":statistics.mean(new),"legacy_worst_mV":max(old),"candidate_worst_mV":max(new),"improved":sum(n<o-1e-8 for o,n in zip(old,new)),"worsened":sum(n>o+1e-8 for o,n in zip(old,new))}
    out["choices"]={name:sum(r["choice"]==name for r in a) for name in sorted({r["choice"] for r in a})}
    return out

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
        row['stable_2s']=stable_gate(t,i,v,old,2.)
        row['stable_5s']=stable_gate(t,i,v,old,5.)
        results.append(row)
        print(json.dumps({"member":row["member"],"old":old["MAE_mV"],"new":new["MAE_mV"],"choice":new["choice"]}),flush=True)
    a=statistics.mean(x["legacy"]["MAE_mV"] for x in results);b=statistics.mean(x["scaled"]["MAE_mV"] for x in results)
    # The previous Windows aggregate is an independent reproduction target, not a fit target.
    assert abs(a-3.9206089537565467)<1e-5,(a,"legacy replay drift")
    summary={"files":24,"legacy_mean_mV":a,"scaled_mean_mV":b,"improved":sum(x["scaled"]["MAE_mV"]<x["legacy"]["MAE_mV"]-1e-8 for x in results),"worsened":sum(x["scaled"]["MAE_mV"]>x["legacy"]["MAE_mV"]+1e-8 for x in results),"legacy_worst_mV":max(x["legacy"]["MAE_mV"] for x in results),"scaled_worst_mV":max(x["scaled"]["MAE_mV"] for x in results)}
    summary["stable_2s"]=summarize_stable(results,"stable_2s")
    summary["stable_5s"]=summarize_stable(results,"stable_5s")
    phase=[r["stable_5s"] for r in results]
    summary["phase_guard_5s"]={}
    for k,base in (("hard","legacy"),("smooth","legacy"),("smooth_discharge","legacy_remaining_discharge"),("smooth_rest","legacy_rest")):
        old=[r[base]["MAE_mV"] for r in phase];new=[r["phase_guard"][k]["MAE_mV"] for r in phase]
        summary["phase_guard_5s"][k]={"mean_mV":statistics.mean(new),"legacy_mean_mV":statistics.mean(old),"worst_mV":max(new),"improved":sum(n<o-1e-8 for o,n in zip(old,new)),"worsened":sum(n>o+1e-8 for o,n in zip(old,new))}
    summary["phase_guard_5s"]["ramp_points"]=sum(r["phase_guard"]["ramp_points"] for r in phase)
    summary["phase_guard_5s"]["max_smooth_minus_hard_mV"]=max(r["phase_guard"]["max_smooth_minus_hard_mV"] for r in phase)
    assert abs(summary["phase_guard_5s"]["hard"]["mean_mV"]-2.4796307575231014)<1e-5
    assert summary["phase_guard_5s"]["smooth_rest"]["worsened"]==0
    peaks=[{"member":r["member"],**r["stable_5s"]["phase_guard"]["peak"]} for r in results]
    summary["peak_diagnosis"]={"worst":max(peaks,key=lambda x:abs(x["signed_error_mV"])),"files":len(peaks)}
    summary["conditional_feedback"]={}
    for h in ("1","5","50"):
        rows=[r["stable_5s"]["phase_guard"]["conditional_feedback"][h] for r in results]
        names=rows[0].keys()
        summary["conditional_feedback"][h]={name:{"mean_MAE_mV":statistics.mean(r[name]["MAE_mV"] for r in rows),"max_mV":max(r[name]["max_mV"] for r in rows),"total_points":sum(r[name]["points"] for r in rows),"over_50mV":sum(r[name]["over_50mV"] for r in rows),"improved_vs_persistence":sum(r[name]["MAE_mV"]<r["persistence"]["MAE_mV"] for r in rows)} for name in names}
    assert abs(abs(summary["peak_diagnosis"]["worst"]["signed_error_mV"])-272.61496143139027)<1e-5

    summary["memory_open_loop"]={}
    for name,base in (("all","smooth"),("discharge","smooth_discharge"),("rest","smooth_rest")):
        a=[r["stable_5s"]["phase_guard"]["memory_open_loop"][name] for r in results]
        b=[r["stable_5s"]["phase_guard"][base] for r in results]
        summary["memory_open_loop"][name]={"mean_MAE_mV":statistics.mean(x["MAE_mV"] for x in a),"baseline_mean_MAE_mV":statistics.mean(x["MAE_mV"] for x in b),"max_mV":max(x["max_mV"] for x in a),"baseline_max_mV":max(x["max_mV"] for x in b),"improved":sum(x["MAE_mV"]<y["MAE_mV"]-1e-8 for x,y in zip(a,b)),"worsened":sum(x["MAE_mV"]>y["MAE_mV"]+1e-8 for x,y in zip(a,b))}

    report={"goal_key":"battery-20261127-hppc-continuous-polarization-memory-v1","archive_sha256":"36a8bd0904a27fd90e44820c5cf938c8e7ed3e01acb6d2232c759b9f07e811cf","scope":"same previously observed 24 low-voltage source files; no independent cell or temperature certification","summary":summary,"results":results}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"result.json").write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    print("SUMMARY",json.dumps(summary),flush=True)

if __name__=="__main__":main()
