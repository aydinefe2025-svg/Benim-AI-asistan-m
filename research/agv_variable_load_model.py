"""Chronological held-out conditional AGV charge prediction, never capacity/SoH."""
import hashlib, json, zipfile, sys, math
from collections import Counter
from pathlib import Path
import numpy as np
PIN='d2986fd9cc6bdeaa21cd0518a5fbc9d1fe6ed5bac2eb173bf547837c5903df51'
SOURCE_JSON_PIN='06ab70c623183062ecfed16cc1f2ede710f009651bf5286d06302f5f1d5c5f9f'
CSV_PIN='13026bae4a98790a45d43fb6ed28ed0c0777adc098647eb07b5d20b9a034964b'
PACKS=[f'FB-{i}' for i in range(10)]

def split(rows):
    rows=[r for r in rows if r['operating_s']>120 and r['days_between_start_dates']<=1]
    dates=sorted({r['date'] for r in rows}); a,b=dates[int(.6*len(dates))],dates[int(.8*len(dates))]
    return ([r for r in rows if r['date']<a], [r for r in rows if r['previous_date']>=a and r['date']<b], [r for r in rows if r['previous_date']>=b],a,b)

def X(rows,kind):
    out=[]
    for r in rows:
        t=r['operating_s']/3600; p=r['previous_operating_s']/3600
        pack=[float(r['pack']==k) for k in PACKS]
        base=[t*x for x in pack]
        if kind=='constant': v=base
        elif kind=='duration': v=base+[max(0,t-k) for k in (.5,1,2)]+[min(t,.5)]
        elif kind=='duration_context': v=base+[max(0,t-k) for k in (.5,1,2)]+[min(t,.5),t*math.log1p(p),t*r['days_between_start_dates']]
        else: raise ValueError(kind)
        out.append(v)
    return np.array(out,dtype=float)

def fit(rows,kind,alpha):
    if set(r['pack'] for r in rows)!=set(PACKS):raise ValueError('missing pack in training')
    x=X(rows,kind); y=np.array([r['delta_Ah'] for r in rows]); return np.linalg.solve(x.T@x+alpha*np.eye(x.shape[1]),x.T@y)
def predict(rows,kind,coef):return np.maximum(0,X(rows,kind)@coef)
def metric(rows,pred):
    y=np.array([r['delta_Ah'] for r in rows]); err=np.abs(pred-y)
    return {'n':len(y),'mae_Ah':float(err.mean()),'rmse_Ah':float(np.sqrt(np.mean(err**2))), 'outside_quantization_1Ah_fraction':float(np.mean(err>1)), 'mean_error_beyond_1Ah':float(np.maximum(err-1,0).mean()), 'bias_Ah':float(np.mean(pred-y))}
def calibration_radius(residuals,alpha):
    r=sorted(float(v) for v in residuals)
    k=math.ceil((len(r)+1)*(1-alpha))
    if not 0<alpha<1 or k>len(r) or k<1:raise ValueError('insufficient calibration sample')
    return r[k-1]
def interval_stats(y,pred,radius):
    y,pred=np.asarray(y),np.asarray(pred)
    lo=np.maximum(0,pred-radius);hi=pred+radius
    covered=(y>=lo)&(y<=hi)
    return {'n':len(y),'covered':int(covered.sum()),'coverage':float(covered.mean()),'mean_width_Ah':float((hi-lo).mean()),'lower_Ah':lo.tolist(),'upper_Ah':hi.tolist()}
def load_source(path):
    raw=Path(path).read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    if zipfile.is_zipfile(path):
        if digest!=PIN: raise ValueError('original CI archive SHA-256 mismatch')
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None: raise ValueError('source ZIP CRC mismatch')
            raw=z.read('AGV_ADJACENT_CURRENT_RECEIPT.json')
    normalized=raw.replace(b'\r\n',b'\n')
    if hashlib.sha256(normalized).hexdigest()!=SOURCE_JSON_PIN:
        raise ValueError('original source receipt SHA-256 mismatch')
    d=json.loads(normalized)
    if (d.get('status')!='AGV_CONDITIONAL_ADJACENT_DISCHARGE_RATE_BOUNDS' or
        d.get('csv_sha256')!=CSV_PIN or d.get('source_rows')!=57880 or
        d.get('adjacent_count')!=988 or len(d.get('pairs',[]))!=988):
        raise ValueError('original source receipt identity mismatch')
    return d,digest

def run(path):
    d,source_digest=load_source(path)
    train,val,test,a,b=split(d['pairs']); assert len(train)*len(val)*len(test)>0
    assert max(r['date'] for r in train)<min(r['previous_date'] for r in val)
    assert max(r['date'] for r in val)<min(r['previous_date'] for r in test)
    candidates=[('constant',0.0)]+[(k,c) for k in ('duration','duration_context') for c in (.1,1.,10.,100.)]
    v=[]
    for k,c in candidates:
        m=metric(val,predict(val,k,fit(train,k,c)));v.append({'kind':k,'alpha':c,**m})
    chosen=min(v,key=lambda r:r['mae_Ah']); kind=chosen['kind']; alpha=chosen['alpha']
    # Refit on training+validation, with boundary rows still purged. Test not used in selection.
    development=train+val; pred0=predict(test,'constant',fit(development,'constant',0)); pred1=predict(test,kind,fit(development,kind,alpha))
    pairs=[{**r,'constant_prediction_Ah':float(q),'selected_prediction_Ah':float(p)} for r,q,p in zip(test,pred0,pred1)]
    by_pack={k:{'constant':metric([r for r in test if r['pack']==k],pred0[[r['pack']==k for r in test]]),'selected':metric([r for r in test if r['pack']==k],pred1[[r['pack']==k for r in test]])} for k in PACKS if any(r['pack']==k for r in test)}
    # Fixed baseline fitted on train only, calibration on validation only.
    # Nonexchangeable time series: empirical coverage, not a formal 90% guarantee.
    base_train=fit(train,'constant',0); pv=predict(val,'constant',base_train)
    residual=np.abs(pv-np.array([r['delta_Ah'] for r in val])); radius=calibration_radius(residual,.1)
    pt=predict(test,'constant',base_train); intervals=interval_stats([r['delta_Ah'] for r in test],pt,radius)
    interval_summary={k:v for k,v in intervals.items() if k not in ('lower_Ah','upper_Ah')}
    for r,p,l,u in zip(pairs,pt,intervals['lower_Ah'],intervals['upper_Ah']):r.update(interval_center_Ah=float(p),interval_lower_Ah=l,interval_upper_Ah=u)
    return {'empirical_90pct_target_interval':{'calibration_n':len(val),'radius_Ah':radius,**interval_summary},'source_sha256':source_digest,'source_receipt_sha256':SOURCE_JSON_PIN,'source_csv_sha256':d['csv_sha256'],'source_rows':d['source_rows'],'source_pairs':988,'eligible':sum(r['operating_s']>120 and r['days_between_start_dates']<=1 for r in d['pairs']), 'train_n':len(train),'validation_n':len(val),'test_n':len(test),'validation_start':a,'test_start':b,'train_date_range':[min(r['date'] for r in train),max(r['date'] for r in train)],'test_date_range':[min(r['date'] for r in test),max(r['date'] for r in test)],'validation_candidates':v,'selected':chosen,'constant_test':metric(test,pred0),'selected_test':metric(test,pred1),'by_pack':by_pack,'test_predictions':pairs,'limits':'Conditional prediction of recorded integer cumulative-Ah difference after operating time is known; not ahead-of-cycle prediction, physical current, capacity, causal aging, or representative fleet data. Purge boundary crossing pairs; no calibration uncertainty.'}
if __name__=='__main__':
    result=run(sys.argv[1]); Path('AGV_VARIABLE_LOAD_MODEL_RECEIPT.json').write_text(json.dumps(result,indent=2,allow_nan=False)); print(json.dumps({k:v for k,v in result.items() if k not in ('test_predictions','by_pack','validation_candidates')},indent=2))